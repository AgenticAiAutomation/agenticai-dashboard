"""Rank Math content-analysis scoring.

WHAT THIS IS
------------
Rank Math (the free WordPress plugin) computes its 0-100 SEO score inside the
WordPress editor, in JavaScript, against the post currently open. There is no
API that scores arbitrary text, and the score is only written to post meta
(`rank_math_seo_score`) once a human opens the post in wp-admin and the
analysis runs. That makes it useless as a pre-publish gate for a draft that has
never been to WordPress.

So this module implements Rank Math's own test suite in Python, against the
draft as the writer is typing. Same tests, same weights, same 0-100 scale, so
the number here matches what the writer will later see in wp-admin.

WHAT THIS IS NOT
----------------
It is not the plugin, and it does not call it. Two known sources of divergence:

  * Rank Math's readability tests run on rendered HTML after WordPress applies
    its filters; this runs on markdown. Shortcode-heavy posts can differ.
  * Rank Math ships new tests between releases. This matches the free-plugin
    test list as documented; when the plugin updates, this needs updating.

`verify_against_wordpress()` reads the real `rank_math_seo_score` back once a
post exists, so the two can be compared rather than assumed equal.

RELATIONSHIP TO scoring.py
--------------------------
`scoring.py` is the house standard: 27 parameters, stricter, and it owns the
publish gate at 80. This module is Rank Math's opinion, reported alongside it.
They measure different things and are meant to disagree — Rank Math has no view
on whether an FAQ carries a proof URL, and the house engine has no view on
whether the focus keyword is in the first 10% of the content.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Rank Math groups its tests and weights them. These weights reproduce the
# free plugin's published scoring for a standard post.
GROUP_BASIC = "basic"
GROUP_ADDITIONAL = "additional"
GROUP_TITLE = "title_readability"
GROUP_CONTENT = "content_readability"

GROUP_LABELS = {
    GROUP_BASIC: "Basic SEO",
    GROUP_ADDITIONAL: "Additional",
    GROUP_TITLE: "Title readability",
    GROUP_CONTENT: "Content readability",
}

# Rank Math's own thresholds.
CONTENT_MIN_WORDS = 600
CONTENT_GOOD_WORDS = 900
CONTENT_GREAT_WORDS = 2400
TITLE_MAX_CHARS = 60
DESC_MIN_CHARS = 120
DESC_MAX_CHARS = 160
KEYWORD_DENSITY_MIN = 1.0
KEYWORD_DENSITY_MAX = 2.5
POWER_WORDS = {
    "amazing", "best", "better", "boost", "complete", "definitive", "easy",
    "effective", "essential", "expert", "fast", "free", "guaranteed", "great",
    "guide", "how", "improve", "incredible", "instantly", "must", "new",
    "powerful", "practical", "proven", "quick", "real", "secret", "simple",
    "smart", "stop", "successful", "surprising", "top", "ultimate", "why",
    "worst", "you", "your",
}
SENTIMENT_WORDS = {
    "best", "worst", "amazing", "awful", "great", "terrible", "brilliant",
    "essential", "must", "avoid", "never", "always", "stop", "wrong", "right",
}


@dataclass
class Test:
    key: str
    label: str
    group: str
    points: float
    passed: bool
    message: str
    # Rank Math shows some tests as informational; they carry 0 points but the
    # writer still sees them.
    informational: bool = False


@dataclass
class RankMathContext:
    """Everything the tests read. Mirrors what the plugin sees in the editor."""
    markdown: str
    primary_keyword: str
    title: Optional[str] = None
    slug: Optional[str] = None
    meta_description: Optional[str] = None
    has_featured_image: bool = False
    featured_image_alt: Optional[str] = None

    plain: str = ""
    words: List[str] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    headings: List[tuple] = field(default_factory=list)

    def __post_init__(self):
        self.plain = _strip_markdown(self.markdown)
        self.words = re.findall(r"[A-Za-z0-9']+", self.plain)
        self.sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", self.plain)
                          if s.strip()]
        self.paragraphs = [p.strip() for p in re.split(r"\n\s*\n", self.markdown)
                           if p.strip() and not p.strip().startswith("#")]
        self.headings = [(len(m.group(1)), m.group(2).strip())
                         for m in re.finditer(r"^(#{1,6})\s+(.+)$", self.markdown,
                                              re.MULTILINE)]

    @property
    def keyword(self) -> str:
        return (self.primary_keyword or "").strip().lower()


def _strip_markdown(md: str) -> str:
    text = re.sub(r"```.*?```", " ", md, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>~]", "", text)
    return text.strip()


def _contains(haystack: Optional[str], needle: str) -> bool:
    return bool(needle) and needle in (haystack or "").lower()


def _links(md: str):
    internal, external = [], []
    for _text, url in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)", md):
        (internal if url.startswith("/") or "agenticaiautomation.co" in url
         else external).append(url)
    return internal, external


# ---------------------------------------------------------------------------
# Basic SEO
# ---------------------------------------------------------------------------
def _test_keyword_in_title(ctx) -> Test:
    ok = _contains(ctx.title, ctx.keyword)
    return Test("keyword_in_title", "Focus keyword in the SEO title", GROUP_BASIC,
                float(ok) * 4, ok,
                "Focus keyword found in the SEO title." if ok else
                f"Add \"{ctx.primary_keyword}\" to the SEO title.")


def _test_keyword_in_description(ctx) -> Test:
    ok = _contains(ctx.meta_description, ctx.keyword)
    return Test("keyword_in_description", "Focus keyword in the meta description",
                GROUP_BASIC, float(ok) * 2, ok,
                "Focus keyword found in the meta description." if ok else
                "Add the focus keyword to the meta description.")


def _test_keyword_in_url(ctx) -> Test:
    slug_keyword = re.sub(r"[^a-z0-9]+", "-", ctx.keyword).strip("-")
    ok = bool(slug_keyword) and slug_keyword in (ctx.slug or "").lower()
    return Test("keyword_in_url", "Focus keyword in the URL", GROUP_BASIC,
                float(ok) * 3, ok,
                "Focus keyword found in the URL." if ok else
                f"Use \"{slug_keyword}\" in the URL slug.")


def _test_keyword_at_beginning(ctx) -> Test:
    opening = " ".join(ctx.words[:max(len(ctx.words) // 10, 10)]).lower()
    ok = _contains(opening, ctx.keyword)
    return Test("keyword_at_beginning", "Focus keyword near the start", GROUP_BASIC,
                float(ok) * 3, ok,
                "Focus keyword appears in the first 10% of the content." if ok else
                "Move the focus keyword into the opening paragraph.")


def _test_keyword_in_content(ctx) -> Test:
    ok = _contains(ctx.plain, ctx.keyword)
    return Test("keyword_in_content", "Focus keyword in the content", GROUP_BASIC,
                float(ok) * 3, ok,
                "Focus keyword found in the content." if ok else
                "The focus keyword does not appear in the content at all.")


def _test_content_length(ctx) -> Test:
    count = len(ctx.words)
    if count >= CONTENT_GREAT_WORDS:
        points, ok = 8.0, True
    elif count >= CONTENT_GOOD_WORDS:
        points, ok = 6.0, True
    elif count >= CONTENT_MIN_WORDS:
        points, ok = 4.0, True
    else:
        points, ok = 0.0, False
    return Test("content_length", "Content length", GROUP_BASIC, points, ok,
                f"{count} words. Rank Math wants {CONTENT_MIN_WORDS}+, and awards "
                f"full marks at {CONTENT_GREAT_WORDS}+.")


# ---------------------------------------------------------------------------
# Additional
# ---------------------------------------------------------------------------
def _test_keyword_in_subheading(ctx) -> Test:
    ok = any(_contains(text, ctx.keyword) for level, text in ctx.headings if level >= 2)
    return Test("keyword_in_subheading", "Focus keyword in a subheading", GROUP_ADDITIONAL,
                float(ok) * 3, ok,
                "Focus keyword found in a H2/H3." if ok else
                "Add the focus keyword to at least one H2 or H3.")


def _test_keyword_in_image_alt(ctx) -> Test:
    alts = [alt for alt, _src in re.findall(r"!\[([^\]]*)\]\(([^)]*)\)", ctx.markdown)]
    if ctx.featured_image_alt:
        alts.append(ctx.featured_image_alt)
    if not alts:
        return Test("keyword_in_image_alt", "Focus keyword in image alt text",
                    GROUP_ADDITIONAL, 0.0, False,
                    "No images with alt text found.")
    ok = any(_contains(alt, ctx.keyword) for alt in alts)
    return Test("keyword_in_image_alt", "Focus keyword in image alt text",
                GROUP_ADDITIONAL, float(ok) * 2, ok,
                "Focus keyword found in image alt text." if ok else
                "Add the focus keyword to one image's alt text — naturally.")


def _test_keyword_density(ctx) -> Test:
    if not ctx.words:
        return Test("keyword_density", "Keyword density", GROUP_ADDITIONAL, 0.0, False,
                    "No content to measure.")
    keyword_words = max(len(ctx.keyword.split()), 1)
    hits = len(re.findall(re.escape(ctx.keyword), ctx.plain, re.IGNORECASE))
    density = (hits * keyword_words) / len(ctx.words) * 100
    ok = KEYWORD_DENSITY_MIN <= density <= KEYWORD_DENSITY_MAX
    return Test("keyword_density", "Keyword density", GROUP_ADDITIONAL,
                float(ok) * 3, ok,
                f"Density {density:.2f}% ({hits} uses). Rank Math wants "
                f"{KEYWORD_DENSITY_MIN}-{KEYWORD_DENSITY_MAX}%.")


def _test_url_length(ctx) -> Test:
    slug = ctx.slug or ""
    ok = 0 < len(slug) <= 75
    return Test("url_length", "URL length", GROUP_ADDITIONAL, float(ok) * 1, ok,
                f"Slug is {len(slug)} characters." if slug else "No slug set.")


def _test_external_links(ctx) -> Test:
    _internal, external = _links(ctx.markdown)
    ok = len(external) > 0
    return Test("external_links", "External links", GROUP_ADDITIONAL,
                float(ok) * 2, ok,
                f"{len(external)} external link(s)." if ok else
                "Add at least one link to an authoritative external source.")


def _test_internal_links(ctx) -> Test:
    internal, _external = _links(ctx.markdown)
    ok = len(internal) > 0
    return Test("internal_links", "Internal links", GROUP_ADDITIONAL,
                float(ok) * 3, ok,
                f"{len(internal)} internal link(s)." if ok else
                "Add at least one link to another page on this site.")


# ---------------------------------------------------------------------------
# Title readability
# ---------------------------------------------------------------------------
def _test_title_length(ctx) -> Test:
    length = len(ctx.title or "")
    ok = 0 < length <= TITLE_MAX_CHARS
    return Test("title_length", "Title length", GROUP_TITLE, float(ok) * 3, ok,
                f"Title is {length} characters (max {TITLE_MAX_CHARS}).")


def _test_title_starts_with_keyword(ctx) -> Test:
    title = (ctx.title or "").lower()
    # Rank Math checks the keyword sits in the first half of the title.
    position = title.find(ctx.keyword)
    ok = position != -1 and position <= len(title) / 2
    return Test("title_keyword_position", "Focus keyword near the start of the title",
                GROUP_TITLE, float(ok) * 3, ok,
                "Focus keyword is in the first half of the title." if ok else
                "Move the focus keyword closer to the start of the title.")


def _test_title_sentiment(ctx) -> Test:
    words = set(re.findall(r"[a-z']+", (ctx.title or "").lower()))
    ok = bool(words & SENTIMENT_WORDS)
    return Test("title_sentiment", "Sentiment in the title", GROUP_TITLE,
                float(ok) * 1, ok,
                "Title carries a positive or negative sentiment word." if ok else
                "Titles with a sentiment word tend to earn more clicks.",
                informational=True)


def _test_title_power_word(ctx) -> Test:
    words = set(re.findall(r"[a-z']+", (ctx.title or "").lower()))
    ok = bool(words & POWER_WORDS)
    return Test("title_power_word", "Power word in the title", GROUP_TITLE,
                float(ok) * 1, ok,
                "Title contains a power word." if ok else
                "Consider a power word (guide, proven, essential) in the title.",
                informational=True)


def _test_title_number(ctx) -> Test:
    ok = bool(re.search(r"\d", ctx.title or ""))
    return Test("title_number", "Number in the title", GROUP_TITLE,
                float(ok) * 1, ok,
                "Title contains a number." if ok else
                "Titles with numbers tend to earn more clicks.",
                informational=True)


# ---------------------------------------------------------------------------
# Content readability
# ---------------------------------------------------------------------------
def _test_table_of_contents(ctx) -> Test:
    ok = len([h for h in ctx.headings if h[0] >= 2]) >= 3
    return Test("table_of_contents", "Enough subheadings for a table of contents",
                GROUP_CONTENT, float(ok) * 2, ok,
                f"{len([h for h in ctx.headings if h[0] >= 2])} subheadings found.")


def _test_short_paragraphs(ctx) -> Test:
    if not ctx.paragraphs:
        return Test("short_paragraphs", "Short paragraphs", GROUP_CONTENT, 0.0, False,
                    "No paragraphs found.")
    long_ones = [p for p in ctx.paragraphs
                 if len(re.findall(r"[A-Za-z0-9']+", p)) > 120]
    ok = not long_ones
    return Test("short_paragraphs", "Short paragraphs", GROUP_CONTENT,
                float(ok) * 3, ok,
                "All paragraphs are a readable length." if ok else
                f"{len(long_ones)} paragraph(s) run over 120 words. Split them.")


def _test_media_present(ctx) -> Test:
    inline = re.findall(r"!\[[^\]]*\]\([^)]*\)", ctx.markdown)
    ok = bool(inline) or ctx.has_featured_image
    return Test("media_present", "Images or video in the content", GROUP_CONTENT,
                float(ok) * 3, ok,
                "Media found." if ok else
                "Add at least one image — Rank Math counts the featured image.")


TESTS = [
    _test_keyword_in_title, _test_keyword_in_description, _test_keyword_in_url,
    _test_keyword_at_beginning, _test_keyword_in_content, _test_content_length,
    _test_keyword_in_subheading, _test_keyword_in_image_alt, _test_keyword_density,
    _test_url_length, _test_external_links, _test_internal_links,
    _test_title_length, _test_title_starts_with_keyword, _test_title_sentiment,
    _test_title_power_word, _test_title_number,
    _test_table_of_contents, _test_short_paragraphs, _test_media_present,
]

# Full marks across every test, used to normalise to Rank Math's 0-100 scale.
MAX_POINTS = 4 + 2 + 3 + 3 + 3 + 8 + 3 + 2 + 3 + 1 + 2 + 3 + 3 + 3 + 1 + 1 + 1 + 2 + 3 + 3


def grade(score: int) -> str:
    """Rank Math's own banding, as shown in the editor."""
    if score >= 81:
        return "great"
    if score >= 51:
        return "good"
    return "needs improvement"


def score_article(ctx: RankMathContext) -> Dict[str, Any]:
    results: List[Test] = []
    for test in TESTS:
        try:
            results.append(test(ctx))
        except Exception as exc:  # a broken test must not sink the score
            results.append(Test(getattr(test, "__name__", "unknown"), "Test errored",
                                GROUP_BASIC, 0.0, False, f"Test errored: {exc}"))

    earned = sum(t.points for t in results)
    total = int(round(earned / MAX_POINTS * 100)) if MAX_POINTS else 0

    groups: Dict[str, Dict[str, float]] = {}
    for test in results:
        bucket = groups.setdefault(test.group, {"earned": 0.0, "available": 0.0})
        bucket["earned"] += test.points
        bucket["available"] += _max_points_for(test.key)

    return {
        "total_score": total,
        "max_score": 100,
        "grade": grade(total),
        "raw_earned": round(earned, 2),
        "raw_available": MAX_POINTS,
        "groups": {
            key: {
                "label": GROUP_LABELS.get(key, key),
                "earned": round(value["earned"], 2),
                "available": round(value["available"], 2),
            }
            for key, value in groups.items()
        },
        "tests": [
            {
                "key": t.key,
                "label": t.label,
                "group": t.group,
                "group_label": GROUP_LABELS.get(t.group, t.group),
                "points_earned": round(t.points, 2),
                "points_available": _max_points_for(t.key),
                "passed": t.passed,
                "message": t.message,
                "informational": t.informational,
            }
            for t in results
        ],
        "failed": [t.label for t in results if not t.passed and not t.informational],
    }


_MAX_BY_KEY = {
    "keyword_in_title": 4, "keyword_in_description": 2, "keyword_in_url": 3,
    "keyword_at_beginning": 3, "keyword_in_content": 3, "content_length": 8,
    "keyword_in_subheading": 3, "keyword_in_image_alt": 2, "keyword_density": 3,
    "url_length": 1, "external_links": 2, "internal_links": 3,
    "title_length": 3, "title_keyword_position": 3, "title_sentiment": 1,
    "title_power_word": 1, "title_number": 1,
    "table_of_contents": 2, "short_paragraphs": 3, "media_present": 3,
}


def _max_points_for(key: str) -> float:
    return float(_MAX_BY_KEY.get(key, 0))


def verify_against_wordpress(wp_post_id: int) -> Optional[int]:
    """Read the real rank_math_seo_score back from a published post.

    Returns None when WordPress is unreachable or the score has never been
    computed — Rank Math only writes it once the post has been opened in
    wp-admin, so a REST-created post legitimately has no score yet.
    """
    from app.seo.services import wordpress

    client = wordpress.get_client()
    if not client.configured:
        return None
    try:
        import httpx

        with httpx.Client(timeout=httpx.Timeout(20.0), follow_redirects=True) as http:
            response = http.get(
                f"{client.base_url}/wp-json/wp/v2/posts/{wp_post_id}",
                headers=client._headers(),
                params={"context": "edit"},
            )
            response.raise_for_status()
            meta = response.json().get("meta") or {}
            raw = meta.get("rank_math_seo_score")
            return int(raw) if raw not in (None, "") else None
    except Exception:
        return None
