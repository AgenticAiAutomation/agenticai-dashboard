"""AI-content detection provider.

Backs the `ai_detection` scoring parameter, which carries 8 of the 100 points —
more than any other single check. Until this module has a provider configured
the parameter is skipped and those 8 points leave the denominator entirely,
so the score is honest about what it did not measure.

Two providers are supported because they disagree, and which one a client
trusts is not ours to decide:

  originality  Originality.ai — /api/v1/scan/ai, returns a 0-1 `fake` score.
  gptzero      GPTZero — /v2/predict/text, returns a 0-1 completely_generated_prob.

Both are paid. Neither is authoritative: detectors produce false positives on
edited human writing and false negatives on lightly-rewritten model output. The
score treats the reading as a signal to investigate, never as proof, and the
detail string says so where a reviewer will read it.
"""
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.seo.services import ServiceUnavailable

TIMEOUT = httpx.Timeout(45.0, connect=10.0)

# Detectors charge per character and get no more accurate past a few thousand
# words. Scanning the opening is what a reader would check anyway.
MAX_CHARS = 20000


@dataclass
class Detection:
    ai_percent: float
    provider: str
    detail: str


def _originality(text: str, api_key: str) -> Detection:
    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.post(
            "https://api.originality.ai/api/v1/scan/ai",
            headers={"X-OAI-API-KEY": api_key},
            json={"content": text, "aiModelVersion": "1"},
        )
        response.raise_for_status()
        body = response.json()

    if not body.get("success", True):
        raise ServiceUnavailable(
            "originality.ai", body.get("error") or "scan rejected")

    score = body.get("score") or {}
    fake = score.get("fake")
    if fake is None:
        raise ServiceUnavailable(
            "originality.ai", f"unexpected response shape: {str(body)[:200]}")

    return Detection(
        ai_percent=round(float(fake) * 100, 1),
        provider="Originality.ai",
        detail=f"Originality.ai scored {float(fake) * 100:.1f}% AI-generated",
    )


def _gptzero(text: str, api_key: str) -> Detection:
    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.post(
            "https://api.gptzero.me/v2/predict/text",
            headers={"x-api-key": api_key},
            json={"document": text},
        )
        response.raise_for_status()
        body = response.json()

    documents = body.get("documents") or []
    if not documents:
        raise ServiceUnavailable(
            "gptzero", f"no document in response: {str(body)[:200]}")

    probability = documents[0].get("completely_generated_prob")
    if probability is None:
        # Newer responses nest the figure under class_probabilities.
        probability = (documents[0].get("class_probabilities") or {}).get("ai")
    if probability is None:
        raise ServiceUnavailable(
            "gptzero", f"unexpected response shape: {str(documents[0])[:200]}")

    return Detection(
        ai_percent=round(float(probability) * 100, 1),
        provider="GPTZero",
        detail=f"GPTZero scored {float(probability) * 100:.1f}% likely AI-generated",
    )


PROVIDERS = {
    "originality": _originality,
    "gptzero": _gptzero,
}


def configured() -> bool:
    provider = (settings.AI_DETECTION_PROVIDER or "").strip().lower()
    return bool(provider in PROVIDERS and settings.AI_DETECTION_API_KEY)


def detect(text: str) -> Optional[Detection]:
    """Return a reading, or None when no provider is configured.

    None means "skip the parameter". Exceptions mean the provider was meant to
    answer and could not — the caller also skips, but says why.
    """
    provider_name = (settings.AI_DETECTION_PROVIDER or "").strip().lower()
    if not provider_name:
        return None
    if provider_name not in PROVIDERS:
        raise ServiceUnavailable(
            "ai-detection",
            f"AI_DETECTION_PROVIDER is {provider_name!r}; expected one of "
            f"{', '.join(sorted(PROVIDERS))}.",
        )
    if not settings.AI_DETECTION_API_KEY:
        raise ServiceUnavailable(
            "ai-detection",
            f"AI_DETECTION_PROVIDER is set to {provider_name} but "
            f"AI_DETECTION_API_KEY is empty.",
        )

    body = text.strip()
    if len(body) < 300:
        raise ServiceUnavailable(
            "ai-detection",
            "Draft is under 300 characters — detectors are unreliable on text "
            "this short and both providers charge per call regardless.",
        )

    try:
        return PROVIDERS[provider_name](body[:MAX_CHARS], settings.AI_DETECTION_API_KEY)
    except httpx.HTTPStatusError as exc:
        raise ServiceUnavailable(
            provider_name,
            f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(provider_name, f"request failed: {exc}")
