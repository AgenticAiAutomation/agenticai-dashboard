"""Conversions between the block array and markdown.

blocks_to_markdown() is a projection, not a format: block articles keep the
blocks as their source and this text exists so the existing 27-parameter
scorer, Rank Math checks and the legacy JSON `html` fallback keep working
without knowing about blocks. Visual blocks project to their text (captions,
alt, labels) so word counts and keyword density see what the reader sees.

markdown_to_blocks() is the migration path for legacy articles. It is
conservative: anything it cannot map with confidence becomes one legacy_html
block, sanitised on render, rather than a guess that changes the page.
"""
from __future__ import annotations

import re
import uuid
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.blog_engine.schema import Block, Run


# ---------------------------------------------------------------------------
# Blocks -> markdown
# ---------------------------------------------------------------------------
def _runs_md(runs: Sequence[Run]) -> str:
    out = []
    for r in runs:
        t = r.text
        types = {m.type: m for m in r.marks}
        if "code" in types:
            t = f"`{t}`"
        if "bold" in types:
            t = f"**{t}**"
        if "italic" in types:
            t = f"*{t}*"
        if "strike" in types:
            t = f"~~{t}~~"
        if "link" in types:
            t = f"[{t}]({types['link'].attrs['href']})"
        out.append(t)
    return "".join(out)


def blocks_to_markdown(blocks: Sequence[Block]) -> str:
    parts: List[str] = []
    for b in blocks:
        t = b.type
        if t == "paragraph":
            parts.append(_runs_md(b.content))
        elif t == "heading":
            parts.append("#" * b.attrs.level + " " + _runs_md(b.content))
        elif t == "key_takeaways":
            parts.append(f"**{b.attrs.title}**\n\n" + "\n".join(f"- {_runs_md(i)}" for i in b.content))
        elif t == "list":
            if b.attrs.style == "numbered":
                parts.append("\n".join(f"{i}. {_runs_md(item.content)}" for i, item in enumerate(b.content, 1)))
            else:
                parts.append("\n".join(f"- {_runs_md(item.content)}" for item in b.content))
        elif t == "steps":
            lines = [f"**{b.attrs.title}**\n" if b.attrs.title else ""]
            for i, s in enumerate(b.content, 1):
                lines.append(f"{i}. **{_runs_md(s.title)}** {_runs_md(s.body)}".rstrip())
            parts.append("\n".join(l for l in lines if l))
        elif t == "image":
            a = b.attrs
            parts.append(f"![{a.alt}]({a.src})" + (f"\n\n*{a.caption}*" if a.caption else ""))
        elif t == "gallery":
            parts.append("\n\n".join(f"![{i.alt}]({i.src})" for i in b.content)
                         + (f"\n\n*{b.attrs.caption}*" if b.attrs.caption else ""))
        elif t == "compare_slider":
            a = b.attrs
            parts.append(f"![{a.before.alt}]({a.before.src})\n\n![{a.after.alt}]({a.after.src})"
                         + (f"\n\n*{a.caption}*" if a.caption else ""))
        elif t == "video":
            a = b.attrs
            url = a.src if a.kind == "file" else f"https://www.youtube.com/watch?v={a.youtube_id}"
            parts.append(f"**{a.title}** — {a.description}\n\n[Watch the video]({url})")
        elif t == "table":
            rows = [[_runs_md(c) for c in row] for row in b.content]
            cols = len(rows[0])
            head = rows[0] if b.attrs.has_header else [""] * cols
            body = rows[1:] if b.attrs.has_header else rows
            md = ["| " + " | ".join(head) + " |", "|" + "---|" * cols]
            md += ["| " + " | ".join(r) + " |" for r in body]
            parts.append(f"*{b.attrs.caption}*\n\n" + "\n".join(md))
        elif t == "callout":
            title = b.attrs.title or b.attrs.kind.title()
            parts.append(f"> **{title}:** {_runs_md(b.content)}")
        elif t == "quote":
            who = ", ".join(x for x in (b.attrs.attribution, b.attrs.role, b.attrs.company) if x)
            parts.append(f"> {_runs_md(b.content)}\n>\n> — {who}")
        elif t == "code":
            parts.append(f"```{b.attrs.language}\n{b.content}\n```")
        elif t == "stat_band":
            parts.append("\n".join(f"- **{s.prefix}{s.value}{s.suffix}** {s.label}" for s in b.content))
        elif t == "chart":
            a = b.attrs
            md = [f"**{a.title}**", "", "| | " + " | ".join(s.name for s in a.series) + " |",
                  "|---|" + "---|" * len(a.series)]
            for i, label in enumerate(a.labels):
                md.append(f"| {label} | " + " | ".join(f"{s.values[i]:g}{a.unit}" for s in a.series) + " |")
            parts.append("\n".join(md))
        elif t == "process_flow":
            flow = " → ".join(n.label for n in b.content)
            parts.append((f"**{b.attrs.title}:** " if b.attrs.title else "") + flow)
        elif t == "faq":
            parts.append(f"## {b.attrs.title}\n\n" + "\n\n".join(
                f"**{i.question}**\n\n{_runs_md(i.answer)}" for i in b.content))
        elif t == "cta":
            a = b.attrs
            parts.append(f"**{a.heading}** {a.text or ''}\n\n[{a.button_label}]({a.href})".rstrip())
        elif t == "divider":
            parts.append("---")
        elif t == "embed":
            a = b.attrs
            parts.append(f"[{a.title or a.provider.title() + ' post'}]({a.url})" + (f" — {a.preview_text}" if a.preview_text else ""))
        elif t == "legacy_html":
            parts.append(re.sub(r"<[^>]+>", " ", b.attrs.html).strip())
    return "\n\n".join(p for p in parts if p.strip()) + "\n"


# ---------------------------------------------------------------------------
# Markdown/HTML -> blocks (migration)
# ---------------------------------------------------------------------------
def new_id() -> str:
    return "blk_" + uuid.uuid4().hex[:8]


_INLINE = {"strong": "bold", "b": "bold", "em": "italic", "i": "italic", "u": "underline",
           "s": "strike", "del": "strike", "code": "code", "sup": "sup", "sub": "sub"}


class _BlockParser(HTMLParser):
    """Walks the converter's HTML and emits blocks.

    Handles the tags the markdown library produces for a text article. Any
    element it does not understand (nested tables, raw HTML, iframes) ends the
    confident run and is captured verbatim into a legacy_html block.
    """

    def __init__(self, faqs: List[Tuple[str, str]], image_dims):
        super().__init__(convert_charrefs=True)
        self.blocks: List[Dict[str, Any]] = []
        self.unknown: List[str] = []       # raw html we could not map
        self.faqs = faqs
        self.image_dims = image_dims
        self.stack: List[str] = []
        self.runs: List[Dict[str, Any]] = []
        self.marks: List[Dict[str, Any]] = []
        self.list_stack: List[Tuple[str, List]] = []
        self.pre = False
        self.code_text = ""
        self.table: Optional[List[List[Any]]] = None
        self.row: Optional[List[Any]] = None
        self.in_blockquote = False

    # -- helpers -----------------------------------------------------------
    def _flush_runs(self, as_type: str = "paragraph", attrs: Optional[Dict] = None) -> None:
        runs = [r for r in self.runs if r["text"]]
        self.runs = []
        if not runs or not "".join(r["text"] for r in runs).strip():
            return
        if self.list_stack:
            self.list_stack[-1][1].append({"content": runs})
            return
        if self.row is not None:
            self.row.append(runs)
            return
        block = {"id": new_id(), "type": as_type, "content": runs}
        if attrs:
            block["attrs"] = attrs
        self.blocks.append(block)

    def _add_text(self, text: str) -> None:
        if not text:
            return
        marks = [dict(m) for m in self.marks]
        if self.runs and self.runs[-1]["marks"] == marks:
            self.runs[-1]["text"] += text
        else:
            self.runs.append({"text": text, "marks": marks})

    # -- parser events -------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.pre:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_runs()
            level = min(max(int(tag[1]), 2), 4)
            self.stack.append(f"h{level}")
        elif tag == "p":
            self._flush_runs()
            self.stack.append("p")
        elif tag in _INLINE:
            self.marks.append({"type": _INLINE[tag]})
        elif tag == "a" and a.get("href"):
            href = a["href"]
            if re.match(r"^(https?://|/|#|mailto:)", href):
                self.marks.append({"type": "link", "attrs": {"href": href}})
            else:
                self.marks.append({"type": "_nolink"})
        elif tag in ("ul", "ol"):
            self._flush_runs()
            self.list_stack.append(("numbered" if tag == "ol" else "bullet", []))
        elif tag == "li":
            self._flush_runs()
        elif tag == "pre":
            self._flush_runs()
            self.pre = True
            self.code_text = ""
        elif tag == "blockquote":
            self._flush_runs()
            self.in_blockquote = True
        elif tag == "table":
            self._flush_runs()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.runs = []
        elif tag == "img":
            self._flush_runs()
            src, alt = a.get("src", ""), (a.get("alt") or "").strip()
            dims = self.image_dims(src) if src else None
            if src and alt and dims:
                self.blocks.append({"id": new_id(), "type": "image", "attrs": {
                    "src": src, "alt": alt, "width": dims[0], "height": dims[1], "layout": "inset"}})
            else:
                self.unknown.append(f'<img src="{src}" alt="{alt}">')
        elif tag == "br":
            self._add_text("\n")
        elif tag == "hr":
            self._flush_runs()
            self.blocks.append({"id": new_id(), "type": "divider", "attrs": {"style": "line"}})
        elif tag in ("thead", "tbody", "div", "span", "figure", "figcaption", "small"):
            pass
        else:
            self.unknown.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag == "pre":
            self.pre = False
            lang = "text"
            m = re.match(r"^\s*", self.code_text)
            self.blocks.append({"id": new_id(), "type": "code", "attrs": {"language": lang},
                                "content": self.code_text.strip("\n")})
            self.code_text = ""
            return
        if self.pre:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(self.stack.pop()[1]) if self.stack else 2
            self._flush_runs("heading", {"level": level})
        elif tag == "p":
            if self.stack and self.stack[-1] == "p":
                self.stack.pop()
            if self.in_blockquote:
                self._flush_runs("callout", {"kind": "info"})
            else:
                self._flush_runs()
        elif tag in _INLINE or tag == "a":
            for i in range(len(self.marks) - 1, -1, -1):
                if self.marks[i]["type"] in (_INLINE.get(tag), "link", "_nolink"):
                    self.marks.pop(i)
                    break
        elif tag == "li":
            self._flush_runs()
        elif tag in ("ul", "ol"):
            self._flush_runs()
            style, items = self.list_stack.pop()
            if items:
                self.blocks.append({"id": new_id(), "type": "list", "attrs": {"style": style}, "content": items})
        elif tag == "blockquote":
            self._flush_runs("callout", {"kind": "info"})
            self.in_blockquote = False
        elif tag in ("td", "th") and self.row is not None:
            runs = [r for r in self.runs if r["text"]] or [{"text": ""}]
            self.row.append(runs)
            self.runs = []
        elif tag == "tr" and self.table is not None and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            self.table = None
            if rows and len({len(r) for r in rows}) == 1:
                self.blocks.append({"id": new_id(), "type": "table",
                                    "attrs": {"caption": "Table", "has_header": True},
                                    "content": rows})
            else:
                self.unknown.append("<table>ragged</table>")

    def handle_data(self, data):
        if self.pre:
            self.code_text += data
            return
        if any(m["type"] == "_nolink" for m in self.marks):
            # A link we refused (odd scheme): keep the words, drop the link.
            saved = self.marks
            self.marks = [m for m in saved if m["type"] != "_nolink"]
            self._add_text(data)
            self.marks = saved
            return
        text = re.sub(r"\s+", " ", data) if not self.runs else re.sub(r"\s+", " ", data)
        if not self.runs and not text.strip():
            return
        self._add_text(text)

    def close(self):
        super().close()
        self._flush_runs()


def markdown_to_blocks(md: str, faqs: Sequence[Tuple[str, str]] = (),
                       image_dims=lambda src: None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Convert an article's markdown to blocks.

    Returns (blocks, notes). `notes` lists what needed a human: unmapped
    markup captured into legacy_html, tables that got a placeholder caption,
    images with no alt or unknown dimensions.
    """
    import markdown as md_lib
    from app.seo.routes.articles import _normalise_markdown  # the same repair the publisher applies

    normalised = _normalise_markdown(md or "")
    # The legacy normaliser treats a '|' line as a block start and puts a blank
    # line before it, which turns a markdown table into paragraphs of pipes.
    # Re-join consecutive table rows. (The legacy render path still has this
    # behaviour; it is left alone so legacy pages stay byte-identical.)
    normalised = re.sub(r"(\n\|[^\n]*)\n\n(?=\|)", lambda m: m.group(1) + "\n", normalised)
    while re.search(r"(\n\|[^\n]*)\n\n(?=\|)", normalised):
        normalised = re.sub(r"(\n\|[^\n]*)\n\n(?=\|)", lambda m: m.group(1) + "\n", normalised)
    html = md_lib.markdown(normalised, extensions=["extra", "sane_lists"])
    parser = _BlockParser(list(faqs), image_dims)
    parser.feed(html)
    parser.close()
    blocks = parser.blocks
    notes: List[str] = []

    for b in blocks:
        if b["type"] == "table" and b["attrs"]["caption"] == "Table":
            notes.append(f"{b['id']}: table needs a real caption")

    if parser.unknown:
        # Rather than guess, keep the original HTML for the whole article in
        # one sanitised block and let a human split it in the editor.
        notes.append(f"{len(parser.unknown)} element(s) could not be mapped "
                     f"({', '.join(sorted(set(parser.unknown))[:5])}); whole body kept as legacy_html")
        blocks = [{"id": new_id(), "type": "legacy_html", "attrs": {"html": html, "source": "markdown"}}]

    if faqs:
        blocks.append({"id": new_id(), "type": "faq", "content": [
            {"question": q, "answer": [{"text": a}]} for q, a in faqs if q.strip()]})
    return blocks, notes
