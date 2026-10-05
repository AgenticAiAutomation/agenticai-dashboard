"""Skim score — an ADVISORY 0-100 measure of how easily a post can be skimmed.

It checks the Blog Playbook format: a TL;DR up top, short question sections,
something visual at least every 300 words, a real example with numbers, a cost
table and a call to action.

Advisory means exactly that. This module is never imported by scoring.py or
rankmath.py, and the publish route never reads it, so a low skim score cannot
block anything and a change here cannot move the house score or the gate.
The dependency runs one way only: it borrows strip_markdown from the house
scorer so both count words identically.

It reads the Markdown conventions the Playbook composer emits
(web/lib/playbook.ts):

    > **TL;DR**              blockquote, then three "> - " bullets
    > **Who this is for:**   one line
    > **Tip:** / **Watch out:** / **Pro tip:** / **Flow:**
    > **Real example:**      client, before, after, numbers
    > **Next step:**         the CTA
    | a | b |                a Markdown table

A hand-written post using the same conventions scores the same way.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.seo.services.scoring import strip_markdown

SECTION_MAX_WORDS = 250
VISUAL_EVERY_WORDS = 300
FIRST_PARAGRAPH_MAX_WORDS = 60

CTA_HOSTS = ("calendly.com", "wa.me/", "api.whatsapp.com", "wa.agenticaiautomation.co")

_WORD = re.compile(r"[A-Za-z0-9']+")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_QUOTE_LABEL = re.compile(r"^\*\*\s*([^*]+?)\s*\*\*")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class Block:
    kind: str                      # heading | quote | table | list | image | paragraph
    lines: List[str] = field(default_factory=list)
    level: int = 0                 # heading level

    @property
    def text(self) -> str:
        if self.kind == "quote":
            return "\n".join(re.sub(r"^\s{0,3}>\s?", "", line) for line in self.lines)
        return "\n".join(self.lines)

    @property
    def words(self) -> int:
        return len(_WORD.findall(strip_markdown(self.text)))

    @property
    def label(self) -> Optional[str]:
        """The bold lead-in of a blockquote: 'tl;dr', 'tip', 'real example'..."""
        if self.kind != "quote":
            return None
        first = self.text.lstrip().split("\n", 1)[0]
        match = _QUOTE_LABEL.match(first)
        if not match:
            return None
        return match.group(1).strip().rstrip(":").strip().lower()


def _kind_of(line: str) -> str:
    stripped = line.strip()
    if _HEADING.match(stripped):
        return "heading"
    if re.match(r"^\s{0,3}>", line):
        return "quote"
    if stripped.startswith("|"):
        return "table"
    if _LIST.match(line):
        return "list"
    if stripped.startswith("!["):
        return "image"
    return "paragraph"


def parse_blocks(markdown: str) -> List[Block]:
    """Split Markdown into top-level blocks. Fenced code is skipped entirely."""
    blocks: List[Block] = []
    current: Optional[Block] = None
    in_fence = False

    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            current = None
            continue
        if in_fence:
            continue
        if not line.strip():
            current = None
            continue

        kind = _kind_of(line)
        if kind == "heading":
            match = _HEADING.match(line.strip())
            blocks.append(Block("heading", [match.group(2)], len(match.group(1))))
            current = None
            continue

        # A paragraph line directly under a list item is that item's
        # continuation, as Markdown reads it.
        if current is not None and (current.kind == kind or
                                    (current.kind == "list" and kind == "paragraph")):
            current.lines.append(line)
            continue

        current = Block(kind, [line])
        blocks.append(current)

    # A run of pipe lines is only a table if it carries a separator row.
    for block in blocks:
        if block.kind == "table" and not any(_TABLE_SEPARATOR.match(l) for l in block.lines):
            block.kind = "paragraph"
    return blocks


def _check(key: str, label: str, available: float, points: float, detail: str) -> Dict[str, Any]:
    points = round(max(0.0, min(points, available)), 1)
    return {"key": key, "label": label, "points_available": available,
            "points_earned": points, "passed": points >= available, "detail": detail}


def _body(blocks: List[Block]) -> List[Block]:
    """Everything after the H1, or everything if there is no H1."""
    for index, block in enumerate(blocks):
        if block.kind == "heading" and block.level == 1:
            return blocks[index + 1:]
    return blocks


def check_tldr(blocks: List[Block], keyword: str) -> Dict[str, Any]:
    quote = next((b for b in blocks if b.label == "tl;dr"), None)
    if quote is None:
        return _check("tldr", "TL;DR with 3 bullets, keyword in the first", 20, 0,
                      "No TL;DR. Open with a '> **TL;DR**' block of three bullets.")
    bullets = [re.sub(r"^\s*[-*+]\s+", "", l) for l in quote.text.split("\n")
               if re.match(r"^\s*[-*+]\s+", l)]
    points, notes = 8.0, []
    if len(bullets) == 3:
        points += 6
    else:
        notes.append(f"{len(bullets)} bullets — use exactly 3")
    if keyword and bullets and keyword.lower() in bullets[0].lower():
        points += 6
    elif not keyword:
        notes.append("set the focus keyword to check the first bullet")
    else:
        notes.append(f'put "{keyword}" in the first bullet')
    return _check("tldr", "TL;DR with 3 bullets, keyword in the first", 20, points,
                  "; ".join(notes) or "TL;DR is in place")


def check_section_length(blocks: List[Block]) -> Dict[str, Any]:
    sections: List[List[Any]] = []          # [heading text, words]
    in_section = False
    for block in blocks:
        if block.kind == "heading" and block.level <= 2:
            in_section = block.level == 2
            if in_section:
                sections.append([block.lines[0], 0])
            continue
        # H3s and below belong to their H2; their own words are not counted.
        if in_section and block.kind != "heading":
            sections[-1][1] += block.words
    if not sections:
        return _check("section_length", f"No H2 section over {SECTION_MAX_WORDS} words",
                      20, 0, "No H2 sections. Break the post into question headings.")
    long = [(title, words) for title, words in sections if words > SECTION_MAX_WORDS]
    points = 20 * (len(sections) - len(long)) / len(sections)
    detail = ("all sections are short enough" if not long else
              "; ".join(f'"{t[:60]}" is {w} words' for t, w in long))
    return _check("section_length", f"No H2 section over {SECTION_MAX_WORDS} words",
                  20, points, detail)


def check_visual_rhythm(blocks: List[Block]) -> Dict[str, Any]:
    runs, current = [], 0
    for block in blocks:
        if block.kind in ("quote", "table", "list", "image"):
            runs.append(current)
            current = 0
        elif block.kind == "paragraph":
            current += block.words
    runs.append(current)
    runs = [r for r in runs if r > 0]
    label = f"Something visual at least every {VISUAL_EVERY_WORDS} words"
    if not runs:
        return _check("visual_rhythm", label, 20, 20, "no long text runs")
    long = [r for r in runs if r > VISUAL_EVERY_WORDS]
    points = 20 * (len(runs) - len(long)) / len(runs)
    detail = ("text is broken up often enough" if not long else
              f"{len(long)} stretch(es) of plain text over {VISUAL_EVERY_WORDS} words "
              f"(longest {max(long)}) — add a list, table, callout or image")
    return _check("visual_rhythm", label, 20, points, detail)


def check_real_example(markdown: str, blocks: List[Block]) -> Dict[str, Any]:
    label = "Real example with at least 2 numbers"
    quote = next((b for b in blocks if b.label == "real example"), None)
    if quote is None:
        if "[REAL EXAMPLE" in (markdown or "").upper():
            return _check("real_example", label, 15, 0,
                          "The [REAL EXAMPLE: ...] placeholder is still there — "
                          "the author fills it with a real client.")
        return _check("real_example", label, 15, 0,
                      "No '> **Real example:**' block. Add a real client with numbers.")
    numbers = _NUMBER.findall(strip_markdown(quote.text))
    if len(numbers) >= 2:
        return _check("real_example", label, 15, 15, f"{len(numbers)} numbers in the example")
    return _check("real_example", label, 15, 5,
                  f"Only {len(numbers)} number(s). Give before/after figures.")


def check_table(blocks: List[Block]) -> Dict[str, Any]:
    present = any(b.kind == "table" for b in blocks)
    return _check("table", "A table (cost & time)", 10, 10 if present else 0,
                  "table present" if present else "Add the cost & time table.")


def check_cta(markdown: str, blocks: List[Block]) -> Dict[str, Any]:
    present = any(b.label == "next step" for b in blocks) or \
        any(host in (markdown or "").lower() for host in CTA_HOSTS)
    return _check("cta", "Call to action", 10, 10 if present else 0,
                  "CTA present" if present else
                  "No call to action. Add a '> **Next step:**' line with a booking link.")


def check_first_paragraph(blocks: List[Block]) -> Dict[str, Any]:
    label = f"First paragraph {FIRST_PARAGRAPH_MAX_WORDS} words or fewer"
    first = next((b for b in blocks if b.kind == "paragraph"
                  and not b.text.lstrip().upper().startswith("[FROM AUTHOR")), None)
    if first is None:
        return _check("first_paragraph", label, 5, 0, "no paragraph found")
    words = first.words
    if words <= FIRST_PARAGRAPH_MAX_WORDS:
        return _check("first_paragraph", label, 5, 5, f"{words} words")
    return _check("first_paragraph", label, 5, 0,
                  f"{words} words — answer the question in {FIRST_PARAGRAPH_MAX_WORDS} or fewer")


def score(markdown: str, primary_keyword: str = "") -> Dict[str, Any]:
    blocks = _body(parse_blocks(markdown))
    checks = [
        check_tldr(blocks, (primary_keyword or "").strip()),
        check_section_length(blocks),
        check_visual_rhythm(blocks),
        check_real_example(markdown, blocks),
        check_table(blocks),
        check_cta(markdown, blocks),
        check_first_paragraph(blocks),
    ]
    total = round(sum(c["points_earned"] for c in checks))
    return {
        "total_score": total,
        "max_score": 100,
        "advisory": True,
        "note": "Advisory — does not block publish",
        "checks": checks,
    }
