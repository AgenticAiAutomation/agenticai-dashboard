"""Inline text: runs with marks -> escaped HTML.

Marks nest in a fixed order (link outermost) so the same runs always produce
the same markup — the renderer is deterministic, which is what makes
"re-render every article" a safe operation.
"""
from __future__ import annotations

import html
import re
from typing import Iterable, List
from urllib.parse import urlparse

from app.blog_engine.schema import Mark, Run

SITE_HOST = "agenticaiautomation.co"

# Outer -> inner.
MARK_ORDER = ("link", "highlight", "emphasis", "code", "bold", "italic",
              "underline", "strike", "sup", "sub")

_TAG = {
    "bold": "strong", "italic": "em", "underline": "u", "strike": "s",
    "code": "code", "sup": "sup", "sub": "sub",
}

_REL_TOKENS = {"nofollow", "noopener", "sponsored", "ugc"}


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def attr(value: str) -> str:
    """Escape for use inside a double-quoted attribute."""
    return html.escape(value, quote=True)


def is_external(href: str) -> bool:
    if not href.startswith(("http://", "https://")):
        return False
    host = urlparse(href).hostname or ""
    return not (host == SITE_HOST or host.endswith("." + SITE_HOST))


def _open(mark: Mark) -> str:
    t = mark.type
    if t == "link":
        href = mark.attrs["href"]
        rel = {tok for tok in str(mark.attrs.get("rel", "")).split() if tok in _REL_TOKENS}
        target = ""
        if is_external(href):
            rel.add("noopener")
        if mark.attrs.get("target") == "_blank":
            target = ' target="_blank"'
            rel.add("noopener")
        rel_attr = f' rel="{" ".join(sorted(rel))}"' if rel else ""
        title = f' title="{attr(str(mark.attrs["title"]))}"' if mark.attrs.get("title") else ""
        return f'<a href="{attr(href)}"{rel_attr}{target}{title}>'
    if t == "highlight":
        return f'<mark class="hl hl-{mark.attrs["token"]}">'
    if t == "emphasis":
        return f'<span class="em em-{mark.attrs["token"]}">'
    return f"<{_TAG[t]}>"


def _close(mark: Mark) -> str:
    t = mark.type
    if t == "link":
        return "</a>"
    if t == "highlight":
        return "</mark>"
    if t == "emphasis":
        return "</span>"
    return f"</{_TAG[t]}>"


def render_runs(runs: Iterable[Run]) -> str:
    out: List[str] = []
    for run in runs:
        marks = sorted(run.marks, key=lambda m: MARK_ORDER.index(m.type))
        # Dedupe by type: two bold marks on one run is one <strong>.
        seen = set()
        ordered = []
        for m in marks:
            if m.type not in seen:
                seen.add(m.type)
                ordered.append(m)
        text = esc(run.text).replace("\n", "<br>")
        out.append("".join(_open(m) for m in ordered) + text
                   + "".join(_close(m) for m in reversed(ordered)))
    return "".join(out)


def text_of(runs: Iterable[Run]) -> str:
    return "".join(r.text for r in runs)


_WORD = re.compile(r"[A-Za-z0-9₹$€£%][A-Za-z0-9'’.,%₹$€£-]*")


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG_STRIP.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "section"
