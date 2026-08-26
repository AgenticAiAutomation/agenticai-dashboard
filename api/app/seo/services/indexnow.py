"""IndexNow submission.

IndexNow tells participating search engines that a URL has appeared, changed or
gone, instead of waiting for them to re-crawl. Bing, Yandex, Seznam and Naver
consume it; Google does not, and no amount of submitting will change that, so
Google still discovers these URLs through the sitemap.

That still matters here: Bing's index is what feeds Microsoft Copilot, so a new
article reaching Bing quickly is the difference between being citable this week
and next month.

Ownership is proved by a key file served from the site root, which already
exists at /<key>.txt. The key is public by design — it only proves that whoever
submits URLs for this host can also write files to it.

Every failure here is swallowed. A search engine being slow, rate-limiting, or
briefly down must never fail a publish: the article is live either way, and the
sitemap remains the durable discovery path.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# IndexNow caps a single submission at 10,000 URLs.
MAX_URLS = 10000


@dataclass
class SubmissionResult:
    submitted: int
    status_code: Optional[int]
    ok: bool
    detail: str


def configured() -> bool:
    return bool(settings.INDEXNOW_KEY)


def submit(urls: List[str]) -> SubmissionResult:
    """Tell IndexNow these URLs changed. Never raises."""
    urls = [u for u in urls if u]
    if not urls:
        return SubmissionResult(0, None, True, "nothing to submit")

    if not configured():
        return SubmissionResult(
            0, None, False,
            "INDEXNOW_KEY is not set, so nothing was submitted. The key file is "
            "already served at /<key>.txt on the site; put the same value in "
            "api/.env to enable this.")

    if len(urls) > MAX_URLS:
        urls = urls[:MAX_URLS]

    payload = {
        "host": settings.INDEXNOW_HOST,
        "key": settings.INDEXNOW_KEY,
        "keyLocation": f"https://{settings.INDEXNOW_HOST}/{settings.INDEXNOW_KEY}.txt",
        "urlList": urls,
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(ENDPOINT, json=payload)
        # 200 accepted, 202 accepted but key still being validated. Both fine.
        ok = response.status_code in (200, 202)
        if not ok:
            logger.warning("IndexNow returned %s: %s",
                           response.status_code, response.text[:200])
        return SubmissionResult(
            submitted=len(urls),
            status_code=response.status_code,
            ok=ok,
            detail=("accepted" if ok else
                    f"rejected ({response.status_code}): {response.text[:160]}"),
        )
    except Exception as exc:
        # Discovery is not worth failing a publish over.
        logger.warning("IndexNow submission failed: %s", exc)
        return SubmissionResult(len(urls), None, False, f"not reachable: {exc}")


def submit_one(url: str) -> SubmissionResult:
    return submit([url])
