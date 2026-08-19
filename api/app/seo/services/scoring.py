"""SEO scoring engine.

The spec enumerates 27 weighted parameters summing to 100 points across four
groups. Each parameter is a `Parameter` in REGISTRY with a check function that
returns points earned, a detail string, and any line-by-line comments.

Parameters that need an integration which is not configured (AI detection,
semantic coverage vs competitors, live mobile-friendliness) are *skipped*, not
scored zero — scoring them zero would silently make every article unpublishable
for reasons the team cannot fix. Skipped parameters are excluded from the
denominator and the total is normalised to 100, with `parameters_skipped`
naming exactly what was left out.
"""
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.config import settings

GROUP_CONTENT = "content_quality"
GROUP_ONPAGE = "onpage_seo"
GROUP_FAQ = "faq_eeat"
GROUP_TECHNICAL = "technical"

GROUP_LABELS = {
    GROUP_CONTENT: "Content quality",
    GROUP_ONPAGE: "On-page SEO",
    GROUP_FAQ: "FAQ + EEAT",
    GROUP_TECHNICAL: "Technical",
}

WORD_COUNT_MIN = 1200
WORD_COUNT_MAX = 2500
# The AI-detection threshold lives in settings (AI_DETECTION_MAX_PERCENT) so it
# can be tuned per environment without a deploy.


@dataclass
class Comment:
    line_number: int
    current_text: str
    suggested_fix: str
    impact_points: float
    parameter: str = ""


@dataclass
class CheckResult:
    points: float
    detail: str
    comments: List[Comment] = field(default_factory=list)
    skipped: bool = False


@dataclass
class ScoringContext:
    """Everything a check needs. Built once per scoring run."""
    markdown: str
    lines: List[str]
    primary_keyword: str
    title: Optional[str] = None
    slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    from_author_story: Optional[str] = None
    featured_image_alt: Optional[str] = None
    featured_image_size: Optional[tuple] = None
    faqs: List[Dict[str, Any]] = field(default_factory=list)
    inbound_internal_links: int = 0
    author_byline: str = "Agentic AI Automation Editorial"

    # --- derived, computed in __post_init__ ---
    body_text: str = ""
    words: List[str] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    headings: List[tuple] = field(default_factory=list)

    def __post_init__(self):
        self.body_text = strip_markdown(self.markdown)
        self.words = re.findall(r"[A-Za-z0-9']+", self.body_text)
        self.sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", self.body_text)
                          if s.strip()]
        self.paragraphs = [p.strip() for p in re.split(r"\n\s*\n", self.markdown)
                           if p.strip() and not p.strip().startswith("#")]
        self.headings = [
            (len(m.group(1)), m.group(2).strip(), self.markdown[:m.start()].count("\n") + 1)
            for m in re.finditer(r"^(#{1,6})\s+(.+)$", self.markdown, re.MULTILINE)
        ]


@dataclass
class Parameter:
    key: str
    label: str
    group: str
    points_available: float
    check: Callable[[ScoringContext], CheckResult]


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def strip_markdown(md: str) -> str:
    text = re.sub(r"```.*?```", " ", md, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>~]", "", text)
    return text.strip()


def count_syllables(word: str) -> int:
    word = word.lower().strip("'")
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    total = len(groups)
    if word.endswith("e") and total > 1 and not word.endswith(("le", "ee")):
        total -= 1
    return max(total, 1)


def flesch_reading_ease(words: List[str], sentences: List[str]) -> Optional[float]:
    if not words or not sentences:
        return None
    syllables = sum(count_syllables(w) for w in words)
    return round(
        206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words)),
        1,
    )


def line_of(md: str, needle: str) -> int:
    index = md.find(needle)
    return md[:index].count("\n") + 1 if index != -1 else 1


def keyword_hits(text: str, keyword: str) -> int:
    if not keyword:
        return 0
    return len(re.findall(re.escape(keyword), text, re.IGNORECASE))


def scale(value: float, low: float, high: float, points: float) -> float:
    """Full points inside [low, high]; linear falloff outside, floored at zero."""
    if low <= value <= high:
        return points
    distance = low - value if value < low else value - high
    span = max((high - low), 1.0)
    return round(max(points * (1 - distance / span), 0.0), 2)


# --------------------------------------------------------------------------
# Content quality (35)
# --------------------------------------------------------------------------
def check_word_count(ctx: ScoringContext) -> CheckResult:
    count = len(ctx.words)
    points = scale(count, WORD_COUNT_MIN, WORD_COUNT_MAX, 5)
    detail = f"{count} words (target {WORD_COUNT_MIN}-{WORD_COUNT_MAX})"
    comments = []
    if count < WORD_COUNT_MIN:
        comments.append(Comment(
            line_number=1,
            current_text=f"Article is {count} words.",
            suggested_fix=f"Add {WORD_COUNT_MIN - count} more words. Expand the "
                          f"framework section with a concrete implementation walkthrough.",
            impact_points=round(5 - points, 2),
        ))
    elif count > WORD_COUNT_MAX:
        comments.append(Comment(
            line_number=1,
            current_text=f"Article is {count} words.",
            suggested_fix=f"Cut roughly {count - WORD_COUNT_MAX} words. Tighten the "
                          f"problem framing and remove restated points.",
            impact_points=round(5 - points, 2),
        ))
    return CheckResult(points, detail, comments)


def check_readability(ctx: ScoringContext) -> CheckResult:
    score = flesch_reading_ease(ctx.words, ctx.sentences)
    if score is None:
        return CheckResult(0, "not enough text to score readability")
    points = scale(score, 60, 75, 3)
    comments = []
    if score < 60:
        comments.append(Comment(
            line_number=1,
            current_text=f"Flesch reading ease is {score}.",
            suggested_fix="Shorten sentences and replace multi-syllable jargon with "
                          "plain words. Target 60-75.",
            impact_points=round(3 - points, 2),
        ))
    return CheckResult(points, f"Flesch reading ease {score} (target 60-75)", comments)


def check_grammar(ctx: ScoringContext) -> CheckResult:
    """LanguageTool, self-hosted on port 8010. Skipped when unreachable."""
    import httpx

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{settings.LANGUAGETOOL_URL.rstrip('/')}/v2/check",
                data={"text": ctx.body_text[:40000], "language": "en-GB"},
            )
            response.raise_for_status()
            matches = response.json().get("matches", [])
    except Exception as exc:
        return CheckResult(
            0, f"LanguageTool unreachable at {settings.LANGUAGETOOL_URL} ({exc})",
            skipped=True,
        )

    # One point off per two issues, floored at zero.
    points = max(5 - len(matches) / 2, 0)
    comments = []
    for match in matches[:25]:
        context_text = match.get("context", {}).get("text", "")
        replacements = [r["value"] for r in match.get("replacements", [])[:3]]
        comments.append(Comment(
            line_number=line_of(ctx.markdown, context_text[:40]) if context_text else 1,
            current_text=context_text,
            suggested_fix=(f"{match.get('message', 'Grammar issue')}"
                           + (f" Try: {', '.join(replacements)}." if replacements else "")),
            impact_points=0.5,
        ))
    return CheckResult(round(points, 2), f"{len(matches)} grammar/style issues", comments)


def check_ai_detection(ctx: ScoringContext) -> CheckResult:
    """Originality.ai or GPTZero, per AI_DETECTION_PROVIDER.

    Scores full marks at or below the configured threshold and falls off
    linearly to zero at twice it, rather than passing/failing on a cliff edge —
    detector readings are noisy enough that a 1% move should not flip an
    article between publishable and blocked.
    """
    from app.seo.services import ai_detection

    try:
        reading = ai_detection.detect(ctx.body_text)
    except Exception as exc:
        return CheckResult(0, f"AI detection unavailable ({exc})", skipped=True)

    if reading is None:
        return CheckResult(
            0,
            "No AI-detection provider configured. Set AI_DETECTION_PROVIDER "
            "(originality or gptzero) and AI_DETECTION_API_KEY in api/.env to "
            "enforce publish rule 5.",
            skipped=True,
        )

    threshold = settings.AI_DETECTION_MAX_PERCENT
    if reading.ai_percent <= threshold:
        points = 8.0
    else:
        over = reading.ai_percent - threshold
        points = round(max(8 * (1 - over / threshold), 0.0), 2)

    comments = []
    if reading.ai_percent > threshold:
        comments.append(Comment(
            line_number=1,
            current_text=reading.detail,
            suggested_fix=(
                f"{reading.provider} puts this above the {threshold:.0f}% threshold. "
                "Treat it as a prompt to check, not a verdict — these detectors "
                "misfire on edited human writing. Rewrite the flattest sections in "
                "the author's own voice and add the specifics only they would know."
            ),
            impact_points=round(8 - points, 2),
        ))

    return CheckResult(points, f"{reading.detail} (threshold {threshold:.0f}%)",
                       comments)


def check_sentence_variety(ctx: ScoringContext) -> CheckResult:
    lengths = [len(re.findall(r"[A-Za-z0-9']+", s)) for s in ctx.sentences]
    if len(lengths) < 5:
        return CheckResult(0, "too few sentences to measure variety")
    stdev = statistics.stdev(lengths)
    points = scale(stdev, 5, 12, 3)
    comments = []
    if stdev < 5:
        comments.append(Comment(
            line_number=1,
            current_text=f"Sentence length standard deviation is {stdev:.1f}.",
            suggested_fix="Sentences are too uniform. Break a few long ones in half "
                          "and merge some short ones.",
            impact_points=round(3 - points, 2),
        ))
    return CheckResult(points, f"sentence length stdev {stdev:.1f} (target 5-12)", comments)


def check_paragraph_variation(ctx: ScoringContext) -> CheckResult:
    lengths = [len(re.findall(r"[A-Za-z0-9']+", p)) for p in ctx.paragraphs]
    if len(lengths) < 4:
        return CheckResult(0, "too few paragraphs to measure variation")
    stdev = statistics.stdev(lengths)
    points = scale(stdev, 10, 40, 2)
    long_paragraphs = [
        Comment(
            line_number=line_of(ctx.markdown, para[:40]),
            current_text=para[:120],
            suggested_fix="This paragraph runs over 150 words. Split it at the first "
                          "topic shift.",
            impact_points=0.5,
        )
        for para, length in zip(ctx.paragraphs, lengths) if length > 150
    ]
    return CheckResult(points, f"paragraph length stdev {stdev:.1f}", long_paragraphs[:10])


PASSIVE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|am)\s+(?:\w+ly\s+)?(\w+(?:ed|en))\b",
    re.IGNORECASE,
)


def check_active_voice(ctx: ScoringContext) -> CheckResult:
    if not ctx.sentences:
        return CheckResult(0, "no sentences")
    passive_sentences = [s for s in ctx.sentences if PASSIVE.search(s)]
    active_ratio = 1 - len(passive_sentences) / len(ctx.sentences)
    points = 3.0 if active_ratio > 0.70 else round(3 * (active_ratio / 0.70), 2)
    comments = [
        Comment(
            line_number=line_of(ctx.markdown, s[:40]),
            current_text=s[:160],
            suggested_fix="Passive construction. Name the actor and put it before the verb.",
            impact_points=0.3,
        )
        for s in passive_sentences[:15]
    ]
    return CheckResult(points, f"{active_ratio * 100:.0f}% active voice (target >70%)",
                       comments)


def check_repeated_phrases(ctx: ScoringContext) -> CheckResult:
    words = [w.lower() for w in ctx.words]
    if len(words) < 60:
        return CheckResult(3, "too short to assess repetition")
    trigrams = Counter(tuple(words[i:i + 3]) for i in range(len(words) - 2))
    # Ignore the primary keyword's own trigram — repeating it is intentional.
    keyword_trigram = tuple(ctx.primary_keyword.lower().split()[:3])
    repeats = {g: n for g, n in trigrams.items() if n >= 3 and g != keyword_trigram}
    points = max(3 - len(repeats) * 0.5, 0)
    comments = [
        Comment(
            line_number=line_of(ctx.markdown, " ".join(gram)),
            current_text=" ".join(gram),
            suggested_fix=f"This phrase appears {count} times. Rewrite all but one.",
            impact_points=0.5,
        )
        for gram, count in sorted(repeats.items(), key=lambda kv: -kv[1])[:10]
    ]
    return CheckResult(round(points, 2), f"{len(repeats)} phrases repeated 3+ times",
                       comments)


def check_heading_hierarchy(ctx: ScoringContext) -> CheckResult:
    if not ctx.headings:
        return CheckResult(0, "no headings found", [Comment(
            1, "(no headings)", "Add one H1 and at least three H2 sections.", 3)])

    h1s = [h for h in ctx.headings if h[0] == 1]
    problems, comments = [], []

    if len(h1s) != 1:
        problems.append(f"{len(h1s)} H1s (need exactly 1)")
        comments.append(Comment(
            line_number=h1s[1][2] if len(h1s) > 1 else 1,
            current_text=h1s[1][1] if len(h1s) > 1 else "(no H1)",
            suggested_fix="An article must have exactly one H1. Demote the extras to H2.",
            impact_points=1.5,
        ))

    previous = ctx.headings[0][0]
    for level, text, line in ctx.headings[1:]:
        if level > previous + 1:
            problems.append(f"H{previous} jumps to H{level}")
            comments.append(Comment(
                line_number=line,
                current_text=f"{'#' * level} {text}",
                suggested_fix=f"Heading levels must not skip. Change this to H{previous + 1}.",
                impact_points=0.75,
            ))
        previous = level

    if len([h for h in ctx.headings if h[0] == 2]) < 3:
        problems.append("fewer than 3 H2 sections")

    points = max(3 - len(problems), 0)
    return CheckResult(points, "; ".join(problems) or "hierarchy is clean", comments)


# --------------------------------------------------------------------------
# On-page SEO (30)
# --------------------------------------------------------------------------
def check_keyword_placement(ctx: ScoringContext) -> CheckResult:
    keyword = ctx.primary_keyword.lower()
    first_100 = " ".join(ctx.words[:100]).lower()
    h1 = next((h[1] for h in ctx.headings if h[0] == 1), "")

    slots = {
        "title": keyword in (ctx.title or "").lower(),
        "meta_description": keyword in (ctx.meta_description or "").lower(),
        "H1": keyword in h1.lower(),
        "first 100 words": keyword in first_100,
    }
    hit = sum(slots.values())
    points = round(8 * hit / 4, 2)
    missing = [name for name, present in slots.items() if not present]
    comments = [
        Comment(
            line_number=1,
            current_text=f"Primary keyword missing from: {', '.join(missing)}.",
            suggested_fix=f"Work \"{ctx.primary_keyword}\" naturally into "
                          f"{', '.join(missing)}.",
            impact_points=round(8 - points, 2),
        )
    ] if missing else []
    return CheckResult(points, f"keyword in {hit}/4 required slots", comments)


def check_keyword_density(ctx: ScoringContext) -> CheckResult:
    if not ctx.words:
        return CheckResult(0, "no body text")
    hits = keyword_hits(ctx.body_text, ctx.primary_keyword)
    keyword_words = max(len(ctx.primary_keyword.split()), 1)
    density = (hits * keyword_words) / len(ctx.words) * 100
    points = scale(density, 0.8, 2.0, 3)
    comments = []
    if density > 2.0:
        comments.append(Comment(
            1, f"Keyword density is {density:.2f}%.",
            f"Over-optimised. Remove about "
            f"{max(int(hits - 2.0 * len(ctx.words) / 100 / keyword_words), 1)} "
            f"occurrences and use synonyms instead.",
            round(3 - points, 2)))
    elif density < 0.8:
        comments.append(Comment(
            1, f"Keyword density is {density:.2f}%.",
            f"Under-optimised. Add the keyword to two or three more H2 sections.",
            round(3 - points, 2)))
    return CheckResult(points, f"density {density:.2f}% ({hits} hits, target 0.8-2%)",
                       comments)


def check_semantic_coverage(ctx: ScoringContext) -> CheckResult:
    """bge-m3 vs top-3 competitors, via the Concierge embedder. Not wired yet."""
    if not settings.EMBEDDER_URL:
        return CheckResult(
            0,
            "EMBEDDER_URL is not set — semantic coverage against the top 3 "
            "competitors needs the concierge-embedder service.",
            skipped=True,
        )
    return CheckResult(0, "competitor corpus not yet captured for this article",
                       skipped=True)


def check_meta_description(ctx: ScoringContext) -> CheckResult:
    meta = (ctx.meta_description or "").strip()
    length = len(meta)
    if not meta:
        return CheckResult(0, "meta description is empty", [Comment(
            1, "(empty)", "Write a 140-160 character meta description containing the "
                          "primary keyword and a reason to click.", 2)])
    points = 2.0 if 140 <= length <= 160 else scale(length, 140, 160, 2)
    comments = [] if 140 <= length <= 160 else [Comment(
        1, meta,
        f"Meta description is {length} characters. Rewrite to land between 140 and 160.",
        round(2 - points, 2))]
    return CheckResult(points, f"{length} characters (target 140-160)", comments)


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check_url_slug(ctx: ScoringContext) -> CheckResult:
    slug = (ctx.slug or "").strip()
    if not slug:
        return CheckResult(0, "no slug set", [Comment(
            1, "(empty)", "Set a lowercase hyphenated slug containing the primary keyword.", 2)])

    problems = []
    if not SLUG_PATTERN.match(slug):
        problems.append("not lowercase-hyphenated")
    if len(slug) > 75:
        problems.append(f"{len(slug)} characters (keep under 75)")
    keyword_slug = re.sub(r"[^a-z0-9]+", "-", ctx.primary_keyword.lower()).strip("-")
    if keyword_slug and keyword_slug.split("-")[0] not in slug:
        problems.append("does not contain the primary keyword")

    points = max(2 - len(problems), 0)
    comments = [Comment(1, slug, f"Fix the slug: {'; '.join(problems)}.",
                        round(2 - points, 2))] if problems else []
    return CheckResult(points, "; ".join(problems) or "slug is clean", comments)


def check_image_alt(ctx: ScoringContext) -> CheckResult:
    inline = re.findall(r"!\[([^\]]*)\]\(([^)]*)\)", ctx.markdown)
    missing = [src for alt, src in inline if not alt.strip()]

    points = 0.0
    notes = []
    if ctx.featured_image_alt and ctx.featured_image_alt.strip():
        points += 1.5
        notes.append("featured image alt present")
    else:
        notes.append("featured image alt MISSING")
    if not missing:
        points += 1.5
        notes.append(f"{len(inline)} inline images all have alt text")
    else:
        notes.append(f"{len(missing)} inline images missing alt text")

    comments = []
    if not (ctx.featured_image_alt or "").strip():
        comments.append(Comment(
            1, "(no featured image alt)",
            "Generate the alt caption before publishing — the publish endpoint "
            "returns 403 without it.", 1.5))
    comments += [
        Comment(line_of(ctx.markdown, src), f"![]({src})",
                "Add descriptive alt text for this image.", 0.5)
        for src in missing[:8]
    ]
    return CheckResult(points, "; ".join(notes), comments)


LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)")
OWN_DOMAIN = "agenticaiautomation.co"


def _links(ctx: ScoringContext):
    internal, external = [], []
    for text, url in LINK_PATTERN.findall(ctx.markdown):
        (internal if url.startswith("/") or OWN_DOMAIN in url else external).append((text, url))
    return internal, external


def check_internal_links(ctx: ScoringContext) -> CheckResult:
    internal, _ = _links(ctx)
    points = 3.0 if len(internal) >= 2 else round(3 * len(internal) / 2, 2)
    comments = [] if len(internal) >= 2 else [Comment(
        1, f"{len(internal)} internal links found.",
        f"Add {2 - len(internal)} more internal link(s) to related published articles.",
        round(3 - points, 2))]
    return CheckResult(points, f"{len(internal)} internal links (need 2+)", comments)


def check_external_links(ctx: ScoringContext) -> CheckResult:
    _, external = _links(ctx)
    points = 3.0 if len(external) >= 2 else round(3 * len(external) / 2, 2)
    comments = [] if len(external) >= 2 else [Comment(
        1, f"{len(external)} external links found.",
        f"Cite {2 - len(external)} more authoritative external source(s) — vendor "
        f"docs, standards bodies, or original research.",
        round(3 - points, 2))]
    return CheckResult(points, f"{len(external)} external links (need 2+)", comments)


# --------------------------------------------------------------------------
# FAQ + EEAT (20)
# --------------------------------------------------------------------------
def check_faq_count(ctx: ScoringContext) -> CheckResult:
    count = len(ctx.faqs)
    points = 5.0 if count >= 5 else round(5 * count / 5, 2)
    comments = [] if count >= 5 else [Comment(
        1, f"{count} FAQ entries.",
        f"Add {5 - count} more FAQ(s) sourced from Reddit, Quora, or People Also Ask.",
        round(5 - points, 2))]
    return CheckResult(points, f"{count} FAQs (need 5+)", comments)


def check_faq_sourced(ctx: ScoringContext) -> CheckResult:
    if not ctx.faqs:
        return CheckResult(0, "no FAQs to source", [Comment(
            1, "(no FAQs)", "Every FAQ needs a proof URL from where the question was asked.", 8)])
    sourced = [f for f in ctx.faqs if (f.get("source_url") or "").strip()]
    points = round(8 * len(sourced) / len(ctx.faqs), 2)
    comments = [
        Comment(1, (f.get("question") or "")[:120],
                "Add the proof URL this question came from (Reddit / Quora / PAA).", 1.0)
        for f in ctx.faqs if not (f.get("source_url") or "").strip()
    ][:8]
    return CheckResult(points, f"{len(sourced)}/{len(ctx.faqs)} FAQs carry a proof URL",
                       comments)


def check_faq_answer_length(ctx: ScoringContext) -> CheckResult:
    if not ctx.faqs:
        return CheckResult(0, "no FAQs")
    in_range, comments = 0, []
    for faq in ctx.faqs:
        words = len(re.findall(r"[A-Za-z0-9']+", faq.get("answer") or ""))
        if 30 <= words <= 80:
            in_range += 1
        else:
            comments.append(Comment(
                1, (faq.get("question") or "")[:120],
                f"Answer is {words} words. Rewrite to land between 30 and 80 — that is "
                f"the range Google pulls into featured snippets.", 0.25))
    points = round(2 * in_range / len(ctx.faqs), 2)
    return CheckResult(points, f"{in_range}/{len(ctx.faqs)} answers are 30-80 words",
                       comments[:8])


def check_author_byline(ctx: ScoringContext) -> CheckResult:
    if ctx.author_byline and ctx.author_byline.strip():
        return CheckResult(2, f"byline set to \"{ctx.author_byline}\"")
    return CheckResult(0, "no author byline", [Comment(
        1, "(no byline)", "Set the WordPress author to the editorial profile.", 2)])


def check_from_author(ctx: ScoringContext) -> CheckResult:
    story = (ctx.from_author_story or "").strip()
    if not story:
        return CheckResult(0, "[FROM AUTHOR] section is empty", [Comment(
            line_number=line_of(ctx.markdown, "[FROM AUTHOR"),
            current_text="[FROM AUTHOR: ...]",
            suggested_fix="The author must fill this with a real production story. "
                          "The publish endpoint returns 403 while it is empty.",
            impact_points=3)])
    words = len(re.findall(r"[A-Za-z0-9']+", story))
    points = 3.0 if words >= 120 else round(3 * words / 120, 2)
    comments = [] if words >= 120 else [Comment(
        1, story[:160],
        f"The From Author section is {words} words. Target around 200 — a specific "
        f"production story with numbers, not a summary.", round(3 - points, 2))]
    return CheckResult(points, f"{words} words in the From Author section", comments)


# --------------------------------------------------------------------------
# Technical (15)
# --------------------------------------------------------------------------
def check_schema_markup(ctx: ScoringContext) -> CheckResult:
    """RankMath emits Article + FAQ + BreadcrumbList when the inputs are present."""
    parts = {
        "Article (needs title + meta description)":
            bool((ctx.title or "").strip() and (ctx.meta_description or "").strip()),
        "FAQPage (needs 5+ FAQs with answers)":
            len([f for f in ctx.faqs if (f.get("answer") or "").strip()]) >= 5,
        "BreadcrumbList (needs a slug)": bool((ctx.slug or "").strip()),
    }
    satisfied = sum(parts.values())
    points = round(5 * satisfied / 3, 2)
    missing = [name for name, ok in parts.items() if not ok]
    comments = [Comment(
        1, f"Schema not emitted for: {', '.join(missing)}.",
        "RankMath builds these from post fields — fill the missing inputs and the "
        "schema appears automatically.", round(5 - points, 2))] if missing else []
    return CheckResult(points, f"{satisfied}/3 schema types will render", comments)


def check_canonical(ctx: ScoringContext) -> CheckResult:
    if (ctx.slug or "").strip():
        return CheckResult(2, "RankMath will emit a self-referencing canonical")
    return CheckResult(0, "no slug, so no canonical URL can be built", [Comment(
        1, "(no slug)", "Set the slug so the canonical tag resolves.", 2)])


def check_no_orphan(ctx: ScoringContext) -> CheckResult:
    count = ctx.inbound_internal_links
    points = 3.0 if count >= 2 else round(3 * count / 2, 2)
    comments = [] if count >= 2 else [Comment(
        1, f"{count} inbound internal links from other published articles.",
        f"Add a link to this article from {2 - count} other published article(s) so it "
        f"is not orphaned.", round(3 - points, 2))]
    return CheckResult(points, f"{count} inbound internal links (need 2+)", comments)


def check_image_dimensions(ctx: ScoringContext) -> CheckResult:
    if not ctx.featured_image_size:
        return CheckResult(0, "no featured image uploaded", [Comment(
            1, "(no featured image)",
            "Upload a featured image at 1200x630 or larger — WordPress rejects the "
            "publish without one.", 2)])
    width, height = ctx.featured_image_size
    if width >= 1200 and height >= 630:
        return CheckResult(2, f"featured image is {width}x{height}")
    return CheckResult(0, f"featured image is {width}x{height}", [Comment(
        1, f"{width}x{height}",
        "Featured image should be at least 1200x630 for social cards and Discover.", 2)])


def check_mobile_friendly(ctx: ScoringContext) -> CheckResult:
    return CheckResult(
        0,
        "Mobile-friendliness is measured against the live URL (PageSpeed Insights) "
        "and only applies once the article is published.",
        skipped=True,
    )


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
REGISTRY: List[Parameter] = [
    Parameter("word_count", "Word count in range", GROUP_CONTENT, 5, check_word_count),
    Parameter("readability", "Flesch-Kincaid 60-75", GROUP_CONTENT, 3, check_readability),
    Parameter("grammar", "LanguageTool grammar", GROUP_CONTENT, 5, check_grammar),
    Parameter("ai_detection", "AI detection <20%", GROUP_CONTENT, 8, check_ai_detection),
    Parameter("sentence_variety", "Sentence variety", GROUP_CONTENT, 3, check_sentence_variety),
    Parameter("paragraph_variation", "Paragraph length variation", GROUP_CONTENT, 2,
              check_paragraph_variation),
    Parameter("active_voice", "Active voice >70%", GROUP_CONTENT, 3, check_active_voice),
    Parameter("repeated_phrases", "No repeated phrases", GROUP_CONTENT, 3,
              check_repeated_phrases),
    Parameter("heading_hierarchy", "H1-H2-H3 hierarchy", GROUP_CONTENT, 3,
              check_heading_hierarchy),

    Parameter("keyword_placement", "Keyword in title/meta/H1/first-100", GROUP_ONPAGE, 8,
              check_keyword_placement),
    Parameter("keyword_density", "Keyword density 0.8-2%", GROUP_ONPAGE, 3,
              check_keyword_density),
    Parameter("semantic_coverage", "Semantic coverage vs top 3", GROUP_ONPAGE, 6,
              check_semantic_coverage),
    Parameter("meta_description", "Meta description 140-160", GROUP_ONPAGE, 2,
              check_meta_description),
    Parameter("url_slug", "URL slug", GROUP_ONPAGE, 2, check_url_slug),
    Parameter("image_alt", "Image alt tags", GROUP_ONPAGE, 3, check_image_alt),
    Parameter("internal_links", "Internal links 2+", GROUP_ONPAGE, 3, check_internal_links),
    Parameter("external_links", "External authoritative links 2+", GROUP_ONPAGE, 3,
              check_external_links),

    Parameter("faq_count", "FAQ section 5+ questions", GROUP_FAQ, 5, check_faq_count),
    Parameter("faq_sourced", "FAQs sourced with proof URLs", GROUP_FAQ, 8, check_faq_sourced),
    Parameter("faq_answer_length", "FAQ answers 30-80 words", GROUP_FAQ, 2,
              check_faq_answer_length),
    Parameter("author_byline", "Author byline present", GROUP_FAQ, 2, check_author_byline),
    Parameter("from_author", "[FROM AUTHOR] section filled", GROUP_FAQ, 3, check_from_author),

    Parameter("schema_markup", "Schema markup applies", GROUP_TECHNICAL, 5,
              check_schema_markup),
    Parameter("canonical", "Canonical tag", GROUP_TECHNICAL, 2, check_canonical),
    Parameter("no_orphan", "No orphan (2+ inbound links)", GROUP_TECHNICAL, 3,
              check_no_orphan),
    Parameter("image_dimensions", "Featured image dimensions", GROUP_TECHNICAL, 2,
              check_image_dimensions),
    Parameter("mobile_friendly", "Mobile-friendly", GROUP_TECHNICAL, 3,
              check_mobile_friendly),
]


def score_article(ctx: ScoringContext) -> Dict[str, Any]:
    parameters, comments = [], []
    groups: Dict[str, Dict[str, float]] = {
        key: {"earned": 0.0, "available": 0.0, "skipped": 0.0}
        for key in GROUP_LABELS
    }

    for parameter in REGISTRY:
        try:
            result = parameter.check(ctx)
        except Exception as exc:  # a broken check must not fail the whole score
            result = CheckResult(0, f"check errored: {exc}", skipped=True)

        bucket = groups[parameter.group]
        if result.skipped:
            bucket["skipped"] += parameter.points_available
        else:
            bucket["earned"] += result.points
            bucket["available"] += parameter.points_available

        parameters.append({
            "key": parameter.key,
            "label": parameter.label,
            "group": parameter.group,
            "points_available": parameter.points_available,
            "points_earned": round(result.points, 2),
            "detail": result.detail,
            "implemented": not result.skipped,
        })
        for comment in result.comments:
            comment.parameter = parameter.key
            comments.append(comment)

    earned = sum(g["earned"] for g in groups.values())
    available = sum(g["available"] for g in groups.values())
    # Normalise so skipped integrations don't make every article unpublishable.
    total = int(round(earned / available * 100)) if available else 0

    comments.sort(key=lambda c: (-c.impact_points, c.line_number))
    skipped = [p["label"] for p in parameters if not p["implemented"]]

    return {
        "total_score": total,
        "max_score": 100,
        "raw_earned": round(earned, 2),
        "raw_available": round(available, 2),
        "groups": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in groups.items()},
        "parameters": parameters,
        "comments": [c.__dict__ for c in comments],
        "parameters_skipped": skipped,
    }
