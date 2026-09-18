"""Blocks -> HTML, once, at publish time.

render_article() turns a block list into the article body plus everything
derived from it (TOC, word count, JSON-LD inputs, asset list). render_page()
wraps that in the marketing site's chrome and returns a complete document the
site serves as a static file. Nothing here reads a database.

All text passes through esc(); the only markup that is not generated here is
the legacy_html block, which goes through the allowlist in sanitize.py.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from app.blog_engine import graphics, sanitize
from app.blog_engine.inline import (attr, esc, is_external, render_runs, slugify,
                                    text_of, word_count)
from app.blog_engine.schema import (Block, Callout, Chart, Code, CompareSlider,
                                    Cta, Divider, Embed, Faq, Gallery, Heading,
                                    Image, ImageAttrs, KeyTakeaways, LegacyHtml,
                                    ListBlock, Paragraph, ProcessFlow, Quote,
                                    StatBand, Steps, Table, Video)

SITE_URL = "https://agenticaiautomation.co"
ENGINE_VERSION = "1.0.0"
WORDS_PER_MINUTE = 220
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Blocks that count as a "visual" for the rhythm rule.
VISUAL_TYPES = {"image", "gallery", "compare_slider", "video", "table", "chart",
                "process_flow", "stat_band", "quote", "callout", "steps", "code"}

# The first blocks are above the fold; they are never given the reveal hook so
# nothing animates before LCP.
ABOVE_FOLD_BLOCKS = 3


@dataclass
class Author:
    name: str
    url: Optional[str] = None
    kind: str = "Organization"          # or "Person"
    job_title: Optional[str] = None
    bio: Optional[str] = None
    photo: Optional[str] = None
    same_as: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)


@dataclass
class ArticleMeta:
    slug: str
    title: str
    meta_title: Optional[str] = None
    meta_description: str = ""
    published_at: str = ""              # ISO 8601
    updated_at: str = ""                # ISO 8601
    author: Author = field(default_factory=lambda: Author(
        name="Agentic AI Automation Editorial", url=SITE_URL + "/#organization"))
    hero: Optional[ImageAttrs] = None
    category: Optional[str] = None
    primary_keyword: Optional[str] = None
    related: List[Tuple[str, str]] = field(default_factory=list)   # (title, url)
    from_author_story: Optional[str] = None
    is_draft: bool = False

    @property
    def canonical(self) -> str:
        return f"{SITE_URL}/blog/{self.slug}"


@dataclass
class TocEntry:
    level: int
    id: str
    text: str


@dataclass
class RenderResult:
    body_html: str
    toc: List[TocEntry]
    word_count: int
    reading_minutes: int
    visuals: int
    assets: List[str]
    headings: List[Tuple[int, str]]
    images: List[ImageAttrs]
    faqs: List[Tuple[str, str]]
    steps: List[Steps]
    videos: List[Video]
    quotes: List[Quote]
    effects: Dict[str, int]
    block_types: List[str]


# ---------------------------------------------------------------------------
# Per-block renderers
# ---------------------------------------------------------------------------
class _Ctx:
    def __init__(self) -> None:
        self.ids: Dict[str, int] = {}
        self.toc: List[TocEntry] = []
        self.words = 0
        self.assets: List[str] = []
        self.images: List[ImageAttrs] = []
        self.faqs: List[Tuple[str, str]] = []
        self.steps: List[Steps] = []
        self.videos: List[Video] = []
        self.quotes: List[Quote] = []
        self.first_image_done = False
        self.effects = {"lead_paragraph": 0, "gradient_headline": 0,
                        "marker_highlight": 0, "breakout": 0}

    def unique_id(self, base: str) -> str:
        n = self.ids.get(base, 0)
        self.ids[base] = n + 1
        return base if n == 0 else f"{base}-{n + 1}"

    def count_words(self, runs) -> None:
        self.words += word_count(text_of(runs))

    def count_highlights(self, runs) -> None:
        self.effects["marker_highlight"] += sum(
            1 for r in runs for m in r.marks if m.type == "highlight")


def _layout(kind: str, ctx: _Ctx) -> str:
    if kind == "breakout":
        ctx.effects["breakout"] += 1
    return f"b-{kind}"


def _picture(img: ImageAttrs, ctx: _Ctx, *, eager: bool = False) -> str:
    """<picture> with srcset from variants; a bare <img> when there are none."""
    ctx.images.append(img)
    ctx.assets.append(img.src)
    ctx.assets.extend(v.src for v in img.variants)
    priority = eager or (img.priority and not ctx.first_image_done)
    loading = 'loading="eager" fetchpriority="high" decoding="sync"' if priority else 'loading="lazy" decoding="async"'
    ctx.first_image_done = ctx.first_image_done or priority
    style = f' style="background-image:url({attr(img.lqip)})"' if img.lqip else ""
    img_tag = (f'<img src="{attr(img.src)}" alt="{attr(img.alt)}" width="{img.width}" '
               f'height="{img.height}" {loading}{style}>')
    if not img.variants:
        return img_tag
    sources = []
    by_format: Dict[str, List] = {}
    for v in img.variants:
        by_format.setdefault(v.format or "jpeg", []).append(v)
    sizes = "(min-width: 1100px) 1100px, 100vw" if img.layout != "inset" else "(min-width: 760px) 68ch, 100vw"
    for fmt in ("avif", "webp", "jpeg", "png"):
        vs = by_format.get(fmt)
        if not vs:
            continue
        srcset = ", ".join(f"{attr(v.src)} {v.width}w" for v in sorted(vs, key=lambda v: v.width))
        if fmt in ("jpeg", "png"):
            # The fallback formats go on the img itself.
            img_tag = img_tag.replace("<img ", f'<img srcset="{srcset}" sizes="{sizes}" ', 1)
        else:
            sources.append(f'<source type="image/{fmt}" srcset="{srcset}" sizes="{sizes}">')
    return f"<picture>{''.join(sources)}{img_tag}</picture>"


def _figure(img: ImageAttrs, ctx: _Ctx, block_id: str, *, eager: bool = False,
            layout: Optional[str] = None) -> str:
    inner = _picture(img, ctx, eager=eager)
    if img.link:
        rel = ' rel="noopener"' if is_external(img.link) else ""
        inner = f'<a href="{attr(img.link)}"{rel}>{inner}</a>'
    cap = ""
    if img.caption or img.credit:
        cap = "<figcaption>" + esc(img.caption or "")
        if img.credit:
            cap += f'<span class="credit">{esc(img.credit)}</span>'
        cap += "</figcaption>"
    return (f'<figure class="b-image {_layout(layout or img.layout, ctx)}" id="{block_id}" data-block="{block_id}">'
            f"{inner}{cap}</figure>")


def r_paragraph(b: Paragraph, ctx: _Ctx) -> str:
    ctx.count_words(b.content)
    ctx.count_highlights(b.content)
    cls = ' class="lead"' if b.attrs.variant == "lead" else ""
    if b.attrs.variant == "lead":
        ctx.effects["lead_paragraph"] += 1
    return f'<p{cls} data-block="{b.id}">{render_runs(b.content)}</p>'


def r_heading(b: Heading, ctx: _Ctx) -> str:
    text = text_of(b.content)
    ctx.count_words(b.content)
    ctx.count_highlights(b.content)
    hid = ctx.unique_id(b.attrs.id or slugify(text))
    ctx.toc.append(TocEntry(b.attrs.level, hid, text))
    cls = ""
    if b.attrs.gradient:
        ctx.effects["gradient_headline"] += 1
        cls = ' class="grad"'
    return f'<h{b.attrs.level} id="{attr(hid)}"{cls} data-block="{b.id}">{render_runs(b.content)}</h{b.attrs.level}>'


def r_key_takeaways(b: KeyTakeaways, ctx: _Ctx) -> str:
    items = []
    for runs in b.content:
        ctx.count_words(runs)
        ctx.count_highlights(runs)
        items.append(f"<li>{render_runs(runs)}</li>")
    return (f'<aside class="b-takeaways" id="{b.id}" data-block="{b.id}" aria-labelledby="{b.id}-t">'
            f'<p class="b-label" id="{b.id}-t">{esc(b.attrs.title)}</p><ul>{"".join(items)}</ul></aside>')


def r_list(b: ListBlock, ctx: _Ctx) -> str:
    tag = "ol" if b.attrs.style == "numbered" else "ul"
    items = []
    for item in b.content:
        ctx.count_words(item.content)
        ctx.count_highlights(item.content)
        if b.attrs.style == "checklist":
            mark = '<span class="chk on" aria-hidden="true"></span><span class="vh">Done: </span>' if item.checked \
                else '<span class="chk" aria-hidden="true"></span>'
            items.append(f'<li class="{"done" if item.checked else ""}">{mark}{render_runs(item.content)}</li>')
        else:
            items.append(f"<li>{render_runs(item.content)}</li>")
    cls = f' class="b-list s-{b.attrs.style}"'
    return f'<{tag}{cls} data-block="{b.id}">{"".join(items)}</{tag}>'


def r_steps(b: Steps, ctx: _Ctx) -> str:
    ctx.steps.append(b)
    out = []
    for i, step in enumerate(b.content, start=1):
        ctx.count_words(step.title)
        ctx.count_words(step.body)
        ctx.count_highlights(step.body)
        img = _figure(step.image, ctx, f"{b.id}-img{i}", layout="inset") if step.image else ""
        body = f"<p>{render_runs(step.body)}</p>" if step.body else ""
        out.append(f'<li id="{b.id}-s{i}"><span class="b-n" aria-hidden="true">{i}</span>'
                   f'<div><p class="st">{render_runs(step.title)}</p>{body}{img}</div></li>')
    title = f'<p class="b-label">{esc(b.attrs.title)}</p>' if b.attrs.title else ""
    return f'<div class="b-steps" id="{b.id}" data-block="{b.id}">{title}<ol>{"".join(out)}</ol></div>'


def r_image(b: Image, ctx: _Ctx) -> str:
    return _figure(b.attrs, ctx, b.id)


def r_gallery(b: Gallery, ctx: _Ctx) -> str:
    figs = "".join(_figure(img, ctx, f"{b.id}-{i}", layout="inset") for i, img in enumerate(b.content, 1))
    cap = f"<figcaption>{esc(b.attrs.caption)}</figcaption>" if b.attrs.caption else ""
    return (f'<figure class="b-gallery n{len(b.content)} {_layout(b.attrs.layout, ctx)}" id="{b.id}" data-block="{b.id}">'
            f'<div class="grid">{figs}</div>{cap}</figure>')


def r_compare_slider(b: CompareSlider, ctx: _Ctx) -> str:
    a = b.attrs
    before = _picture(a.before, ctx)
    after = _picture(a.after, ctx)
    cap = f"<figcaption>{esc(a.caption)}</figcaption>" if a.caption else ""
    # Without JS this is two labelled images side by side; the slider script
    # (Phase 5) turns the same markup into the drag view. Content identical.
    return (f'<figure class="b-compare {_layout(a.layout, ctx)}" id="{b.id}" data-block="{b.id}" '
            f'style="aspect-ratio:{a.before.width}/{a.before.height}">'
            f'<div class="pane before"><span class="b-tag">{esc(a.label_before)}</span>{before}</div>'
            f'<div class="pane after"><span class="b-tag">{esc(a.label_after)}</span>{after}</div>'
            f'<input class="handle" type="range" min="0" max="100" value="50" aria-label="Compare {attr(a.label_before)} and {attr(a.label_after)}" hidden>'
            f"{cap}</figure>")


def r_video(b: Video, ctx: _Ctx) -> str:
    a = b.attrs
    ctx.videos.append(b)
    ctx.assets.append(a.poster)
    cap = f"<figcaption>{esc(a.caption)}</figcaption>" if a.caption else ""
    if a.kind == "file":
        ctx.assets.append(a.src or "")
        ext = (a.src or "").rsplit(".", 1)[-1].lower()
        mime = "video/webm" if ext == "webm" else "video/mp4"
        flags = "muted loop playsinline" if a.loop else "controls playsinline"
        inner = (f'<video {flags} preload="none" poster="{attr(a.poster)}" width="{a.width}" height="{a.height}" '
                 f'aria-label="{attr(a.title)}"><source src="{attr(a.src)}" type="{mime}">'
                 f'<p>Your browser cannot play this clip. <a href="{attr(a.src)}">Download it</a>.</p></video>')
    else:
        # Facade: a real link to the video, with the poster. The Phase 5 script
        # swaps in the iframe on click; without it the link simply opens YouTube.
        url = f"https://www.youtube-nocookie.com/embed/{a.youtube_id}?autoplay=1"
        inner = (f'<a class="yt" href="{url}" data-yt="{a.youtube_id}" rel="noopener" '
                 f'style="aspect-ratio:{a.width}/{a.height}">'
                 f'<img src="{attr(a.poster)}" alt="" width="{a.width}" height="{a.height}" loading="lazy" decoding="async">'
                 f'<span class="play" aria-hidden="true"></span><span class="vh">Play video: {esc(a.title)}</span></a>')
    return (f'<figure class="b-video k-{a.kind} {_layout(a.layout, ctx)}" id="{b.id}" data-block="{b.id}">'
            f"{inner}{cap}</figure>")


def r_table(b: Table, ctx: _Ctx) -> str:
    a = b.attrs
    rows = b.content
    align = a.align or ["left"] * len(rows[0])
    header_texts = [text_of(c) for c in rows[0]] if a.has_header else []

    def cell(tag: str, runs, ci: int, ri: int) -> str:
        ctx.count_words(runs)
        cls = f' class="ta-{align[ci]}"' if align[ci] != "left" else ""
        scope = ' scope="col"' if tag == "th" else ""
        label = f' data-label="{attr(header_texts[ci])}"' if (a.mobile == "stack" and header_texts and tag == "td") else ""
        return f"<{tag}{cls}{scope}{label}>{render_runs(runs)}</{tag}>"

    parts = [f"<caption>{esc(a.caption)}</caption>"]
    body_rows = rows
    if a.has_header:
        parts.append("<thead><tr>" + "".join(cell("th", c, ci, 0) for ci, c in enumerate(rows[0])) + "</tr></thead>")
        body_rows = rows[1:]
    parts.append("<tbody>" + "".join(
        "<tr>" + "".join(cell("td", c, ci, ri) for ci, c in enumerate(row)) + "</tr>"
        for ri, row in enumerate(body_rows, 1)) + "</tbody>")
    sortable = ' data-sortable="1"' if a.sortable else ""
    return (f'<div class="b-table m-{a.mobile} {_layout(a.layout, ctx)}" id="{b.id}" data-block="{b.id}">'
            f'<div class="scroll" tabindex="0" role="region" aria-label="{attr(a.caption)}">'
            f'<table{sortable}>{"".join(parts)}</table></div></div>')


def r_callout(b: Callout, ctx: _Ctx) -> str:
    ctx.count_words(b.content)
    ctx.count_highlights(b.content)
    default_titles = {"info": "Note", "tip": "Tip", "warning": "Watch out", "result": "Result"}
    title = b.attrs.title or default_titles[b.attrs.kind]
    return (f'<aside class="b-callout k-{b.attrs.kind}" id="{b.id}" data-block="{b.id}" role="note">'
            f'<p class="b-label">{esc(title)}</p><p>{render_runs(b.content)}</p></aside>')


def r_quote(b: Quote, ctx: _Ctx) -> str:
    ctx.count_words(b.content)
    ctx.quotes.append(b)
    who = esc(b.attrs.attribution)
    meta = ", ".join(x for x in (b.attrs.role, b.attrs.company) if x)
    cite = f'<cite>{who}' + (f'<span>{esc(meta)}</span>' if meta else "") + "</cite>"
    return (f'<figure class="b-quote" id="{b.id}" data-block="{b.id}"><blockquote><p>{render_runs(b.content)}</p></blockquote>'
            f"<figcaption>{cite}</figcaption></figure>")


def r_code(b: Code, ctx: _Ctx) -> str:
    cap = esc(b.attrs.caption) if b.attrs.caption else ""
    head = f'<figcaption><span class="lang">{esc(b.attrs.language)}</span>{cap}' \
           f'<button type="button" class="copy" hidden>Copy</button></figcaption>'
    return (f'<figure class="b-code" id="{b.id}" data-block="{b.id}">{head}'
            f'<pre><code class="language-{attr(b.attrs.language)}">{esc(b.content)}</code></pre></figure>')


def r_stat_band(b: StatBand, ctx: _Ctx) -> str:
    items = []
    for i, s in enumerate(b.content):
        ctx.words += word_count(s.label)
        count = f' data-count="{s.numeric:g}"' if s.numeric is not None else ""
        items.append(f'<div class="b-stat"><p class="num"{count}><span class="pre">{esc(s.prefix)}</span>'
                     f'<span class="v">{esc(s.value)}</span><span class="suf">{esc(s.suffix)}</span></p>'
                     f'<p class="b-lbl">{esc(s.label)}</p></div>')
    return f'<div class="b-stats n{len(items)}" id="{b.id}" data-block="{b.id}">{"".join(items)}</div>'


def r_chart(b: Chart, ctx: _Ctx) -> str:
    a = b.attrs
    src = f'<p class="src">Source: {esc(a.source)}</p>' if a.source else ""
    return (f'<figure class="b-chart {_layout(a.layout, ctx)}" id="{b.id}" data-block="{b.id}">'
            f'<figcaption class="b-label">{esc(a.title)}</figcaption>{graphics.chart(a, b.id)}{src}</figure>')


def r_process_flow(b: ProcessFlow, ctx: _Ctx) -> str:
    return (f'<figure class="b-flow {_layout(b.attrs.layout, ctx)}" id="{b.id}" data-block="{b.id}">'
            + (f'<figcaption class="b-label">{esc(b.attrs.title)}</figcaption>' if b.attrs.title else "")
            + f'<div class="scroll">{graphics.process_flow(b.content, b.id, b.attrs.title)}</div></figure>')


def r_faq(b: Faq, ctx: _Ctx) -> str:
    items = []
    for i, item in enumerate(b.content):
        ctx.words += word_count(item.question)
        ctx.count_words(item.answer)
        ctx.faqs.append((item.question, text_of(item.answer)))
        items.append(f'<details class="faq"{" open" if i == 0 else ""}><summary>{esc(item.question)}</summary>'
                     f"<div><p>{render_runs(item.answer)}</p></div></details>")
    return (f'<section class="b-faq" id="{b.id}" data-block="{b.id}" aria-labelledby="{b.id}-t">'
            f'<h2 id="{b.id}-t">{esc(b.attrs.title)}</h2>{"".join(items)}</section>')


def r_cta(b: Cta, ctx: _Ctx) -> str:
    a = b.attrs
    text = f"<p>{esc(a.text)}</p>" if a.text else ""
    rel = ' rel="noopener"' if is_external(a.href) else ""
    return (f'<aside class="b-cta k-{a.kind}" id="{b.id}" data-block="{b.id}"><p class="h">{esc(a.heading)}</p>{text}'
            f'<a class="btn btn-hot" href="{attr(a.href)}"{rel}>{esc(a.button_label)}</a></aside>')


def r_divider(b: Divider, ctx: _Ctx) -> str:
    return f'<hr class="b-divider s-{b.attrs.style}" data-block="{b.id}">'


def r_embed(b: Embed, ctx: _Ctx) -> str:
    a = b.attrs
    prov = "LinkedIn" if a.provider == "linkedin" else "X"
    title = f'<p class="t">{esc(a.title)}</p>' if a.title else ""
    preview = f"<p>{esc(a.preview_text)}</p>" if a.preview_text else ""
    return (f'<a class="b-embed p-{a.provider}" id="{b.id}" data-block="{b.id}" href="{attr(a.url)}" rel="noopener" target="_blank">'
            f'<span class="prov">{prov}</span>{title}{preview}<span class="b-open">Open on {prov} ↗</span></a>')


def r_legacy_html(b: LegacyHtml, ctx: _Ctx) -> str:
    cleaned = sanitize.clean(b.attrs.html)
    ctx.words += word_count(_strip_tags(cleaned))
    return f'<div class="b-legacy" id="{b.id}" data-block="{b.id}">{cleaned}</div>'


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


RENDERERS = {
    Paragraph: r_paragraph, Heading: r_heading, KeyTakeaways: r_key_takeaways,
    ListBlock: r_list, Steps: r_steps, Image: r_image, Gallery: r_gallery,
    CompareSlider: r_compare_slider, Video: r_video, Table: r_table,
    Callout: r_callout, Quote: r_quote, Code: r_code, StatBand: r_stat_band,
    Chart: r_chart, ProcessFlow: r_process_flow, Faq: r_faq, Cta: r_cta,
    Divider: r_divider, Embed: r_embed, LegacyHtml: r_legacy_html,
}


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------
def render_article(blocks: Sequence[Block]) -> RenderResult:
    ctx = _Ctx()
    parts: List[str] = []
    visuals = 0
    for index, block in enumerate(blocks):
        html = RENDERERS[type(block)](block, ctx)
        if block.type in VISUAL_TYPES:
            visuals += 1
        # Reveal hook only below the fold; the Phase 5 script animates these,
        # and without it (or with reduced motion) they are simply visible.
        if index >= ABOVE_FOLD_BLOCKS and block.type not in ("divider",):
            html = html.replace(" data-block=", " data-reveal data-block=", 1)
        parts.append(html)
    words = ctx.words
    return RenderResult(
        body_html="\n".join(parts),
        toc=ctx.toc,
        word_count=words,
        reading_minutes=max(1, math.ceil(words / WORDS_PER_MINUTE)),
        visuals=visuals,
        assets=[a for a in ctx.assets if a],
        headings=[(t.level, t.text) for t in ctx.toc],
        images=ctx.images,
        faqs=ctx.faqs,
        steps=ctx.steps,
        videos=ctx.videos,
        quotes=ctx.quotes,
        effects=ctx.effects,
        block_types=[b.type for b in blocks],
    )


def render_toc(toc: List[TocEntry]) -> str:
    entries = [t for t in toc if t.level in (2, 3)]
    if len(entries) < 3:
        return ""
    items = "".join(f'<li class="l{t.level}"><a href="#{attr(t.id)}">{esc(t.text)}</a></li>' for t in entries)
    return (f'<nav class="b-toc" aria-labelledby="toc-t"><details open><summary id="toc-t">On this page</summary>'
            f"<ol>{items}</ol></details></nav>")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def _read(name: str) -> str:
    with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _display_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return f"{dt.day} {dt:%B %Y}"


def _date_only(iso: str) -> str:
    return iso[:10] if iso else ""


def _inline_script_hashes(html: str) -> List[str]:
    """sha256 (base64) of each inline <script> body, for the CSP."""
    import base64
    import hashlib
    out = []
    for body in re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S):
        out.append(base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode())
    return out


DEFERRED_CSS_URL_BASE = "/static/blog/engine"


def render_page(blocks: Sequence[Block], meta: ArticleMeta, *,
                analytics: bool = True, preferred_sources: bool = True,
                chrome_version: str = "2026-09-18") -> Tuple[str, RenderResult]:
    """A complete document: chrome + head + article + JSON-LD. Returns (html, result).

    The critical stylesheet is inlined; the block styles are linked as a
    content-hashed file the publisher writes next to the media, so every
    article shares one cached copy.
    """
    from app.blog_engine import css as css_mod
    from app.blog_engine import seo  # imported here: seo depends on this module's types

    css = css_mod.build_critical()
    deferred_href = f"{DEFERRED_CSS_URL_BASE}/{css_mod.deferred_filename()}"

    result = render_article(blocks)
    jsonld = seo.build(meta, result)
    page = _read("page.html")
    header = _read("_chrome_header.html")
    footer = _read("_chrome_footer.html")

    title = meta.meta_title or meta.title
    og_image = f"{SITE_URL}{meta.hero.src}" if meta.hero and meta.hero.src.startswith("/") else (meta.hero.src if meta.hero else f"{SITE_URL}/static/images/og-default.png")
    og_alt = meta.hero.alt if meta.hero else "Agentic AI Automation"

    hero = ""
    if meta.hero:
        ctx = _Ctx()
        hero = _figure(meta.hero, ctx, "hero", eager=True, layout="inset")

    updated = ""
    if meta.updated_at and _date_only(meta.updated_at) > _date_only(meta.published_at):
        updated = (f'<span class="sep" aria-hidden="true">&middot;</span><span class="updated-on">Updated '
                   f'<time datetime="{attr(meta.updated_at)}">{esc(_display_date(meta.updated_at))}</time></span>')

    related = ""
    if meta.related:
        items = "".join(f'<li><a href="{attr(u)}">{esc(t)}</a></li>' for t, u in meta.related)
        related = f'<section class="postnext"><h2>Read next</h2><ul>{items}</ul></section>'

    from_author = ""
    if meta.from_author_story:
        from_author = (f'<aside class="fromauthor"><p class="kicker"><span class="pip"></span>From the author</p>'
                       f"<p>{esc(meta.from_author_story)}</p></aside>")

    author_box = ""
    a = meta.author
    if a.kind == "Person":
        photo = f'<img src="{attr(a.photo)}" alt="" width="72" height="72" loading="lazy">' if a.photo else ""
        creds = "".join(f"<li>{esc(c)}</li>" for c in a.credentials)
        links = "".join(f'<a href="{attr(u)}" rel="me noopener">{esc(u.split("//")[-1].split("/")[0])}</a>' for u in a.same_as)
        author_box = (f'<aside class="b-author">{photo}<div><p class="b-n">{esc(a.name)}</p>'
                      + (f'<p class="t">{esc(a.job_title)}</p>' if a.job_title else "")
                      + (f"<p>{esc(a.bio)}</p>" if a.bio else "")
                      + (f'<ul class="b-creds">{creds}</ul>' if creds else "")
                      + (f'<p class="links">{links}</p>' if links else "") + "</div></aside>")

    analytics_html = _read("_analytics.html") if analytics else ""
    # The GA snippet has an inline <script>; hashing it keeps the policy strict
    # while letting exactly that snippet run. If the snippet changes, the hash
    # follows it automatically.
    inline_hashes = " ".join(f"'sha256-{h}'" for h in _inline_script_hashes(analytics_html))
    csp = (f"default-src 'self'; script-src 'self' {inline_hashes} https://www.googletagmanager.com https://news.google.com; "
           "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://www.google-analytics.com https://i.ytimg.com https://www.gstatic.com; "
           "font-src 'self'; connect-src 'self' https://www.google-analytics.com https://analytics.google.com "
           "https://www.googletagmanager.com; frame-src https://www.youtube-nocookie.com https://news.google.com; "
           "object-src 'none'; base-uri 'self'; form-action 'self'")

    ps_script = '<script async src="https://news.google.com/swg/js/v1/publisher.js"></script>' if preferred_sources else ""
    ps_block = ('<div class="pref-source"><p class="pref-source__label">Follow this source on Google</p>'
                '<div google-add-preferred-source-btn data-theme="dark"></div></div>') if preferred_sources else ""

    robots = "noindex, follow" if meta.is_draft else "index, follow, max-image-preview:large"
    draft = ('<div class="narrow"><p class="draftnote"><strong>Draft preview.</strong> Not indexed, not in the '
             "sitemap and not listed on the blog.</p></div>") if meta.is_draft else ""

    fills = {
        "TITLE": esc(title),
        "DESCRIPTION": attr(meta.meta_description),
        "CANONICAL": attr(meta.canonical),
        "OG_IMAGE": attr(og_image),
        "OG_IMAGE_ALT": attr(og_alt),
        "ROBOTS": robots,
        "CSP": csp,
        "ANALYTICS": analytics_html,
        "PREFERRED_SOURCES_SCRIPT": ps_script,
        "CSS": css,
        "CSS_DEFERRED_HREF": attr(deferred_href),
        "JSONLD": "\n".join(f'<script type="application/ld+json">{json.dumps(d, ensure_ascii=False)}</script>' for d in jsonld),
        "HEADER": header,
        "ARTICLE_TITLE": esc(meta.title),
        "DRAFT": draft,
        "PUBLISHED_ISO": attr(meta.published_at),
        "PUBLISHED_DISPLAY": esc(_display_date(meta.published_at)),
        "UPDATED": updated,
        "READING_MINUTES": str(result.reading_minutes),
        "AUTHOR_NAME": esc(a.name),
        "HERO": hero,
        "TOC": render_toc(result.toc),
        "BODY": result.body_html,
        "FROM_AUTHOR": from_author,
        "AUTHOR_BOX": author_box,
        "RELATED": related,
        "FOOTER": footer.replace("{{PREFERRED_SOURCE}}", ps_block),
        "ENGINE_META": f'<meta name="generator" content="blog-engine {ENGINE_VERSION}; chrome {chrome_version}">',
        "WORD_COUNT": str(result.word_count),
    }
    # Check the template's placeholders against the fills before substituting,
    # so a code block that legitimately contains "{{" cannot trip the check.
    wanted = set(re.findall(r"{{([A-Z_]+)}}", page))
    missing = wanted - set(fills)
    if missing:
        raise RuntimeError(f"page.html has unfilled placeholders: {sorted(missing)}")
    for key, value in fills.items():
        page = page.replace("{{" + key + "}}", value)
    return page, result
