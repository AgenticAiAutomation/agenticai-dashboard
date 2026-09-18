"""Allowlist sanitiser for the one block that carries HTML: legacy_html.

Every other block is structured data and is escaped on render, so this is
the only place user-supplied markup can reach the page. The allowlist is
deliberately narrow — the tags the markdown converter emits for an existing
article and nothing else. No style, no class, no event handlers, no iframes,
no SVG, no data: URLs on images.

nh3 (the maintained successor to bleach, Rust-backed) does the parsing. If it
is ever missing the block renders as escaped text rather than as HTML: an
ugly article beats an XSS.
"""
from __future__ import annotations

import html
import re

try:
    import nh3
except ImportError:  # pragma: no cover - exercised only on a broken install
    nh3 = None

ALLOWED_TAGS = {
    "p", "br", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "pre", "code", "a", "img", "figure",
    "figcaption", "table", "thead", "tbody", "tr", "th", "td", "caption",
    "hr", "sup", "sub", "small", "span", "details", "summary",
}

ALLOWED_ATTRS = {
    # rel is not allowlisted: nh3 sets link_rel on every anchor instead, and
    # refuses to do both. Legacy markdown output never carried rel anyway.
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "th": {"scope", "colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
    "ol": {"start"},
    "details": {"open"},
    "code": {"class"},   # language-xxx from the converter
}

URL_SCHEMES = {"http", "https", "mailto"}

_LANG_CLASS = re.compile(r"^language-[a-z0-9+#-]{1,20}$")


def _attribute_filter(tag: str, attribute: str, value: str):
    """Drop anything the allowlist admits by name but not by value."""
    if tag == "code" and attribute == "class":
        return value if _LANG_CLASS.match(value) else None
    if tag == "a" and attribute == "target":
        return "_blank" if value == "_blank" else None
    if tag == "img" and attribute == "src" and not re.match(r"^(https?://|/)", value):
        return None
    if tag == "img" and attribute == "loading":
        return value if value in {"lazy", "eager"} else None
    return value


def clean(raw: str) -> str:
    """Return HTML safe to place inside the article body."""
    if not raw:
        return ""
    if nh3 is None:
        return f"<pre>{html.escape(raw)}</pre>"
    out = nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        url_schemes=URL_SCHEMES,
        link_rel="noopener",
        attribute_filter=_attribute_filter,
        strip_comments=True,
    )
    # An <img> whose src was rejected renders nothing and trips every
    # accessibility check; drop it. One with a src but no alt is decorative
    # until a writer says otherwise, so it gets alt="" rather than no alt.
    out = re.sub(r"<img(?![^>]*\bsrc=)[^>]*>", "", out)
    out = re.sub(r"<img(?![^>]*\balt=)", '<img alt=""', out)
    # Every img the converter emitted becomes lazy unless it said otherwise;
    # legacy articles have no LCP candidate in the body.
    return re.sub(r"<img(?![^>]*\bloading=)", '<img loading="lazy" decoding="async"', out)
