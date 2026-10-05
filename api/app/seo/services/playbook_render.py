"""Markdown -> HTML for Blog Playbook posts, used at publish time.

The legacy converter (routes/articles.py `_markdown_to_html`) stays exactly as
it is for every other article. It inserts a blank line before every block-level
line, which suits hand-typed drafts but breaks two things the Playbook format
relies on:

  * every table row becomes its own paragraph, so tables never render;
  * Python-Markdown folds neighbouring blockquotes into one, so the TL;DR and
    "Who this is for" would arrive at the site as a single box.

This converter keeps runs of the same kind of line together (table rows,
quoted lines, list items) and gives each blockquote its own element, so the
site's `playbook_html` filter can style each one. It only runs when the flag
is on for the publisher AND the body opens with a TL;DR block — an old post
can never reach it — and any failure falls back to the legacy converter.
"""
import re
import xml.etree.ElementTree as etree
from typing import List

_TLDR = re.compile(r"^\s{0,3}>\s?\*\*\s*TL;DR\s*:?\s*\*\*", re.IGNORECASE)


def is_playbook(md: str) -> bool:
    """True when the body opens (after the H1) with a '> **TL;DR**' block."""
    for line in (md or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("# "):
            continue
        return bool(_TLDR.match(line))
    return False


def _line_kind(line: str) -> str:
    stripped = line.lstrip()
    if re.match(r"^\s{0,3}>", line):
        return "quote"
    if stripped.startswith("|"):
        return "table"
    if re.match(r"^\s*(?:[-*+]|\d+[.)])\s", line):
        return "list"
    return "other"


def normalise(md: str) -> str:
    """Same repair as the legacy normaliser, minus splitting a block apart.

    A blank line is still added before any block-level line that follows a
    paragraph, and after every heading. It is not added between two lines of
    the same table, blockquote or list.
    """
    numbered_heading = re.compile(r"^\*\*\s*(\d+)\.\s+(.+?)\s*\*\*\s*$")
    bold_heading = re.compile(r"^\*\*\s*([^*]+?)\s*\*\*\s*$")
    block_start = re.compile(r"^(#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|>\s|>$|\|)")

    out: List[str] = []
    inside_fence = False

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            out.append(line)
            continue
        if inside_fence:
            out.append(line)
            continue

        match = numbered_heading.match(line)
        if match:
            line = f"### {match.group(1)}. {match.group(2)}"
        elif bold_heading.match(line) and len(line) < 90:
            line = f"### {bold_heading.match(line).group(1)}"

        previous = out[-1] if out else ""
        same_run = (previous.strip() and _line_kind(line) != "other"
                    and _line_kind(line) == _line_kind(previous))
        if block_start.match(line) and previous.strip() and not same_run:
            out.append("")

        out.append(line)
        if line.startswith("#"):
            out.append("")

    return "\n".join(out)


def _separate_quotes_extension():
    from markdown.blockprocessors import BlockQuoteProcessor
    from markdown.extensions import Extension

    class SeparateQuoteProcessor(BlockQuoteProcessor):
        """A blockquote never merges into the one before it."""

        def run(self, parent, blocks):
            block = blocks.pop(0)
            m = self.RE.search(block)
            if m:
                before = block[:m.start()]
                self.parser.parseBlocks(parent, [before])
                block = "\n".join(self.clean(line)
                                  for line in block[m.start():].split("\n"))
            quote = etree.SubElement(parent, "blockquote")
            self.parser.state.set("blockquote")
            self.parser.parseChunk(quote, block)
            self.parser.state.reset()

    class SeparateQuotes(Extension):
        def extendMarkdown(self, md):
            md.parser.blockprocessors.register(SeparateQuoteProcessor(md.parser),
                                               "quote", 20)

    return SeparateQuotes()


# A placeholder line still in the body means the author-review step did not
# substitute the story into it. The site prints from_author_story in its own
# "From the author" box, so the bracketed instruction is dropped rather than
# published as text.
_LEFTOVER_FROM_AUTHOR = re.compile(r"^[ \t]*\[FROM AUTHOR:[^\]\n]*\][ \t]*$", re.MULTILINE)


def to_html(md: str) -> str:
    import markdown as md_lib
    md = _LEFTOVER_FROM_AUTHOR.sub("", md)
    return md_lib.markdown(normalise(md),
                           extensions=["extra", "sane_lists", "toc",
                                       _separate_quotes_extension()])
