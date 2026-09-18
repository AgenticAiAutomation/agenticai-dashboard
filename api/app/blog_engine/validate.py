"""Publish-time validators for a block article.

Two severities. `block` stops a publish; `warn` shows in the editor and costs
score but does not stop anything. The split follows the work order: exceed
an effect limit and you get a warning; fail a contrast or alt-text rule and
you cannot publish. Unlimited freedom produces unreadable pages, and the
whole point of this engine is pages people actually read.

Everything here works on the parsed blocks and the RenderResult, so it runs
identically in the editor (on save) and in the publish endpoint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.blog_engine.css import tokens
from app.blog_engine.inline import text_of, word_count
from app.blog_engine.render import ArticleMeta, RenderResult, VISUAL_TYPES
from app.blog_engine.schema import Block, Heading, Paragraph

META_TITLE_MAX = 60
META_DESC_MIN, META_DESC_MAX = 140, 160
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STOP_WORDS = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are"}


@dataclass
class Violation:
    level: str            # "block" | "warn"
    rule: str
    message: str
    block_id: Optional[str] = None

    def __str__(self) -> str:
        where = f" [{self.block_id}]" if self.block_id else ""
        return f"{self.level.upper()} {self.rule}{where}: {self.message}"


def _effect_limits(blocks: Sequence[Block], result: RenderResult) -> List[Violation]:
    out: List[Violation] = []
    limits = tokens()["effects"]

    if result.effects["gradient_headline"] > limits["gradient_headline"]["limit_per_article"]:
        out.append(Violation("warn", "effect.gradient_headline",
                             f"{result.effects['gradient_headline']} gradient headlines; the limit is "
                             f"{limits['gradient_headline']['limit_per_article']} per article"))
    if result.effects["marker_highlight"] > limits["marker_highlight"]["limit_per_article"]:
        out.append(Violation("warn", "effect.marker_highlight",
                             f"{result.effects['marker_highlight']} marker highlights; the limit is "
                             f"{limits['marker_highlight']['limit_per_article']} per article — "
                             "more than that and nothing stands out"))

    # Lead paragraphs: one per section, where a section starts at each h2
    # (or at the top of the article).
    per_section = 0
    section_id = "top"
    for b in blocks:
        if isinstance(b, Heading) and b.attrs.level == 2:
            per_section, section_id = 0, b.id
        elif isinstance(b, Paragraph) and b.attrs.variant == "lead":
            per_section += 1
            if per_section > limits["lead_paragraph"]["limit_per_section"]:
                out.append(Violation("warn", "effect.lead_paragraph",
                                     "a second lead paragraph in the same section", b.id))
    return out


def _rhythm(blocks: Sequence[Block], result: RenderResult) -> List[Violation]:
    """The anti-wall-of-text rule."""
    out: List[Violation] = []
    r = tokens()["rhythm"]

    # Words since the last visual block.
    run, run_start = 0, None
    for b in blocks:
        if b.type in VISUAL_TYPES:
            run, run_start = 0, None
            continue
        words = _block_words(b)
        if words and run_start is None:
            run_start = b.id
        run += words
        if run > r["max_words_between_visuals"]:
            out.append(Violation("warn", "rhythm.wall_of_text",
                                 f"{run} words since the last visual element (limit {r['max_words_between_visuals']}); "
                                 "add an image, table, chart, callout or quote", run_start))
            run, run_start = 0, None   # report once per stretch

    if result.word_count >= r["words_per_visual"]:
        needed = result.word_count // r["words_per_visual"]
        if result.visuals < needed:
            out.append(Violation("warn", "rhythm.visual_density",
                                 f"{result.visuals} visual elements for {result.word_count} words; "
                                 f"the rule is at least 1 per {r['words_per_visual']} words ({needed} needed)"))

    if r["require_key_takeaways_above_fold"]:
        early = [b.type for b in blocks[:4]]
        if "key_takeaways" not in early:
            out.append(Violation("warn", "rhythm.key_takeaways",
                                 "no key_takeaways block in the first four blocks — it targets the featured "
                                 "snippet and the AI overview, and it needs to be above the fold"))

    if r["require_faq"] and "faq" not in result.block_types:
        out.append(Violation("warn", "rhythm.faq", "no faq block; every article needs one"))
    return out


def _block_words(b: Block) -> int:
    if b.type in ("paragraph", "callout", "quote"):
        return word_count(text_of(b.content))
    if b.type == "heading":
        return word_count(text_of(b.content))
    if b.type == "list":
        return sum(word_count(text_of(i.content)) for i in b.content)
    if b.type == "key_takeaways":
        return sum(word_count(text_of(i)) for i in b.content)
    return 0


def _structure(blocks: Sequence[Block], result: RenderResult) -> List[Violation]:
    out: List[Violation] = []
    # Heading levels must not skip: h2 -> h4 with no h3 between.
    last = 1
    for b in blocks:
        if isinstance(b, Heading):
            if b.attrs.level > last + 1:
                out.append(Violation("block", "structure.heading_skip",
                                     f"h{b.attrs.level} follows h{last}; heading levels cannot skip", b.id))
            last = b.attrs.level
    if not any(isinstance(b, Heading) and b.attrs.level == 2 for b in blocks):
        out.append(Violation("warn", "structure.no_sections",
                             "no h2 headings; the article has no sections and no table of contents"))

    # Images: the schema already enforces alt presence/length/filename; here
    # we catch the lazy alt that passes those checks.
    for img in result.images:
        if len(img.alt.split()) < 3:
            out.append(Violation("block", "image.alt_quality",
                                 f"alt text \"{img.alt}\" is too thin to describe the image; write what is in it"))
    return out


def _meta(meta: ArticleMeta) -> List[Violation]:
    out: List[Violation] = []
    title = meta.meta_title or meta.title
    if len(title) > META_TITLE_MAX:
        out.append(Violation("block", "meta.title_length",
                             f"meta title is {len(title)} characters; keep it to {META_TITLE_MAX}"))
    d = len(meta.meta_description or "")
    if not META_DESC_MIN <= d <= META_DESC_MAX:
        out.append(Violation("block", "meta.description_length",
                             f"meta description is {d} characters; it needs to be {META_DESC_MIN}-{META_DESC_MAX}"))
    if not SLUG.match(meta.slug):
        out.append(Violation("block", "meta.slug", "slug must be lowercase words joined by single hyphens"))
    else:
        parts = meta.slug.split("-")
        stops = sum(1 for p in parts if p in STOP_WORDS)
        if len(parts) > 8 or (parts and stops / len(parts) > 0.4):
            out.append(Violation("warn", "meta.slug_soup",
                                 f"slug has {len(parts)} words, {stops} of them stop words; shorten it"))
    return out


def _links(result: RenderResult, body_html: str) -> List[Violation]:
    out: List[Violation] = []
    hrefs = re.findall(r'<a [^>]*href="([^"]+)"', body_html)
    internal = [h for h in hrefs if h.startswith("/") or "agenticaiautomation.co" in h]
    if len(internal) < 3:
        out.append(Violation("warn", "links.internal",
                             f"{len(internal)} internal links; the target is 3 or more, all resolving"))
    return out


def validate_article(blocks: Sequence[Block], meta: ArticleMeta,
                     result: RenderResult) -> List[Violation]:
    """Every violation, blocks first, then warnings, in a stable order."""
    found: List[Violation] = []
    found += _structure(blocks, result)
    found += _meta(meta)
    found += _effect_limits(blocks, result)
    found += _rhythm(blocks, result)
    found += _links(result, result.body_html)
    found.sort(key=lambda v: (0 if v.level == "block" else 1, v.rule))
    return found


def blocking(violations: Sequence[Violation]) -> List[Violation]:
    return [v for v in violations if v.level == "block"]
