"""Claude client for draft generation, alt captions, and audit interpretation.

Model is Claude Sonnet 4.6 per the SEO Operations spec (settings.ANTHROPIC_MODEL).
Every call is metered into seo_api_usage so the daily INR budget cap is
enforceable before the request is made, not discovered on the invoice.
"""
import base64
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.seo import enums
from app.seo.matrix import COUNTRY_LABELS, VERTICAL_LABELS
from app.seo.services import ServiceUnavailable

# Sonnet 4.6 list price, USD per million tokens.
USD_PER_MTOK_INPUT = 3.0
USD_PER_MTOK_OUTPUT = 15.0
# Rough conversion for the ₹500/day cap. Not a financial rate — a budget guard.
INR_PER_USD = 88.0


@dataclass
class ClaudeResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_inr: float


def _cost_inr(input_tokens: int, output_tokens: int) -> float:
    usd = (input_tokens / 1_000_000) * USD_PER_MTOK_INPUT + \
          (output_tokens / 1_000_000) * USD_PER_MTOK_OUTPUT
    return round(usd * INR_PER_USD, 4)


def spend_today(db: Session) -> float:
    from app.seo.models import SeoApiUsage

    total = (
        db.query(func.coalesce(func.sum(SeoApiUsage.cost_inr), 0))
        .filter(SeoApiUsage.date == date.today(), SeoApiUsage.provider == "anthropic")
        .scalar()
    )
    return float(total or 0)


def check_budget(db: Session) -> None:
    spent = spend_today(db)
    if spent >= settings.SEO_DAILY_BUDGET_INR:
        raise ServiceUnavailable(
            "anthropic",
            f"Daily Claude budget of ₹{settings.SEO_DAILY_BUDGET_INR:.0f} is exhausted "
            f"(₹{spent:.2f} spent today). Generation resumes at 00:00 UTC.",
        )


def record_usage(db: Session, result: ClaudeResult, operation: str,
                 article_id: Optional[Any] = None) -> None:
    from app.seo.models import SeoApiUsage

    db.add(SeoApiUsage(
        date=date.today(),
        provider="anthropic",
        operation=operation,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_inr=Decimal(str(result.cost_inr)),
        article_id=article_id,
    ))


def _client():
    if not settings.ANTHROPIC_API_KEY:
        raise ServiceUnavailable(
            "anthropic",
            "ANTHROPIC_API_KEY is not set in api/.env — draft generation and alt "
            "captions are unavailable until it is.",
        )
    try:
        import anthropic
    except ImportError:
        raise ServiceUnavailable("anthropic", "the `anthropic` package is not installed")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _call(messages: List[Dict[str, Any]], system: str, max_tokens: int = 16000,
          effort: str = "medium") -> ClaudeResult:
    client = _client()
    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            messages=messages,
        )
    except Exception as exc:  # surfaced to the caller as a 503, not a 500
        raise ServiceUnavailable("anthropic", str(exc))

    if response.stop_reason == "refusal":
        raise ServiceUnavailable("anthropic", "the model declined this request")

    text = "".join(block.text for block in response.content if block.type == "text")
    return ClaudeResult(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_inr=_cost_inr(response.usage.input_tokens, response.usage.output_tokens),
    )


# --------------------------------------------------------------------------
# Draft generation
# --------------------------------------------------------------------------
DRAFT_SYSTEM = """You are the senior SEO content strategist for Agentic AI Automation, \
an agency selling WhatsApp automation, RPA, n8n workflow automation, and agentic AI \
implementation services.

You write the AUTHOR DRAFT: a structured, near-publishable article that a two-person \
SEO team will then edit. Your draft must be specific, technical, and grounded in real \
implementation detail — never generic listicle filler.

Hard requirements for every draft:
- The primary keyword appears in the title, the H1, and the first 100 words, naturally.
- Keyword density stays between 0.8% and 2%. Do not stuff.
- Structure with a single H1, then H2s, then H3s. Never skip a level.
- Write in active voice for at least 70% of sentences. Vary sentence length.
- Target Flesch-Kincaid reading ease of 60-75: short paragraphs, plain words.
- Include a literal placeholder line exactly as written:
  [FROM AUTHOR: 200 words on real production story about {topic}]
- The FAQ section must carry 5-8 questions, each with the real source URL it came from.
- Never invent a source URL. If you do not have a real one, omit the URL field entirely
  rather than fabricating it.

Return ONLY a single JSON object, no prose before or after, matching this shape:
{
  "title": str,
  "slug": str,
  "meta_title": str,
  "meta_description": str,
  "buyer_intent": "informational" | "commercial" | "transactional",
  "body_md": str,
  "faqs": [{"question": str, "answer": str, "source_url": str|null, "source_platform": str|null}],
  "internal_link_targets": [str],
  "external_link_targets": [str],
  "featured_image_concept": str
}

`body_md` is the full article in Markdown: storyline hook (~100 words referencing the \
captured pain point), problem framing (~200 words), the framework/solution section \
(800-1200 words with H2/H3), the [FROM AUTHOR: ...] placeholder, then the CTA block. \
Do not put the FAQ inside body_md — it goes in the `faqs` array."""


def build_draft_prompt(
    *,
    article_type: enums.ArticleType,
    vertical: enums.Vertical,
    country: Optional[enums.Country],
    primary_keyword: str,
    title_hint: Optional[str],
    source_platform: Optional[str],
    source_url: Optional[str],
    captured_question: Optional[str],
    keyword_difficulty: Optional[int],
    monthly_search_volume: Optional[int],
    competitor_urls: Optional[List[str]],
    published_titles: List[str],
) -> str:
    vertical_label = VERTICAL_LABELS.get(vertical, vertical.value)
    lines = [
        f"Article type: {article_type.value}",
        f"Vertical: {vertical_label}",
        f"Primary keyword: {primary_keyword}",
    ]

    if article_type == enums.ArticleType.onpage and country is not None:
        country_label = COUNTRY_LABELS.get(country, country.value)
        lines += [
            f"Target country: {country_label}",
            "",
            f"This is an ONPAGE article. Geo-localise the title, the H1, and the CTA to "
            f"{country_label}. Use {country_label} spelling, currency, regulations, and "
            f"business context. The CTA must be commercial — book a call, request an "
            f"audit — and localised to {country_label}.",
        ]
    else:
        lines += [
            "",
            "This is a CONTENT article: general education, no country lock. Do not "
            "mention a specific country as the target market. The CTA is informational "
            "— subscribe, read the related guide, download the checklist.",
        ]

    if title_hint:
        lines.append(f"\nWorking title from the team: {title_hint}")
    if captured_question:
        lines.append(
            f"\nThis article answers a real question captured from "
            f"{source_platform or 'a community'}:\n\"{captured_question}\""
            f"\nThe storyline hook must reference the pain point behind that question."
        )
    if source_url:
        lines.append(f"Source URL: {source_url}")
    if keyword_difficulty is not None:
        lines.append(f"Ubersuggest keyword difficulty: {keyword_difficulty}")
    if monthly_search_volume is not None:
        lines.append(f"Ubersuggest monthly search volume: {monthly_search_volume}")
    if competitor_urls:
        lines.append("Top competitor URLs to out-cover (do not copy):")
        lines += [f"  - {u}" for u in competitor_urls[:5]]

    if published_titles:
        lines.append(
            "\nSuggest at least 2 internal link targets from these already-published "
            "articles (use the exact titles):"
        )
        lines += [f"  - {t}" for t in published_titles[:25]]
    else:
        lines.append(
            "\nNo articles are published yet, so leave internal_link_targets empty "
            "rather than inventing links."
        )

    return "\n".join(lines)


def _extract_json(text: str) -> Dict[str, Any]:
    """Pull the JSON object out of a response that may carry stray prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ServiceUnavailable("anthropic", "model did not return a JSON object")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ServiceUnavailable("anthropic", f"model returned malformed JSON: {exc}")


def generate_draft(prompt: str) -> tuple[Dict[str, Any], ClaudeResult]:
    result = _call(
        messages=[{"role": "user", "content": prompt}],
        system=DRAFT_SYSTEM,
        max_tokens=16000,
        effort="high",
    )
    return _extract_json(result.text), result


# --------------------------------------------------------------------------
# Alt caption (vision)
# --------------------------------------------------------------------------
ALT_SYSTEM = """You write image alt text for SEO. Return ONLY the alt text — no \
quotes, no label, no explanation.

Rules:
- 8 to 15 words.
- Describe what is actually visible in the image. Never describe what you assume.
- Include the primary keyword naturally, only where it genuinely fits the image.
- Never start with "Image of" or "Picture of".
- Plain sentence case, no trailing period."""


def generate_alt_caption(
    *,
    image_bytes: bytes,
    mime_type: str,
    title: str,
    primary_keyword: str,
    context: str,
) -> tuple[str, ClaudeResult]:
    prompt = (
        f"Article title: {title}\n"
        f"Primary keyword: {primary_keyword}\n"
        f"Surrounding context:\n{context[:1500]}\n\n"
        "Write the alt text for the attached featured image."
    )
    result = _call(
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64.standard_b64encode(image_bytes).decode(),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
        system=ALT_SYSTEM,
        max_tokens=200,
        effort="low",
    )
    return result.text.strip().strip('"'), result
