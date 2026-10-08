"""Standalone HTML export of an article that has passed the score threshold.

One self-contained file: inline CSS, the featured image embedded as a data
URI, no scripts, no external requests. It opens offline, can be emailed, and
can be pasted into another system. The body goes through the same converter
the publish step uses (routes/articles.py `_publish_html`), so the export
matches what would go live.

Always light: this is a document people outside the team read.

Read-only. Nothing here touches scoring, the publish gate or the publisher.
"""
import base64
import html
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# The bracketed author instruction is never meant to be read; the story is
# rendered in its own box below the body.
_FROM_AUTHOR_LINE = re.compile(r"^[ \t]*\[FROM AUTHOR:[^\]\n]*\][ \t]*$", re.MULTILINE)

# Same labels and classes as the site's playbook_html filter (AgenticWeb blog.py).
PLAYBOOK_CLASSES = {
    "tl;dr": "pb-tldr", "who this is for": "pb-who", "tip": "pb-tip",
    "watch out": "pb-warn", "pro tip": "pb-tip", "real example": "pb-example",
    "flow": "pb-flow", "next step": "pb-cta",
}
_LABELLED_QUOTE = re.compile(r"<blockquote>(\s*<p>\s*<strong>([^<]{1,40})</strong>)")
_TABLE = re.compile(r"<table>.*?</table>", re.DOTALL)

CSS = """
:root{color-scheme:light only}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:#1d1d22;font:17px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:40px 20px 64px}
.meta{font-size:13px;color:#6b6b75;margin:0 0 28px;padding-bottom:16px;border-bottom:1px solid #e6e4df}
h1{font-size:34px;line-height:1.2;margin:0 0 12px;letter-spacing:-.01em}
h2{font-size:24px;line-height:1.3;margin:40px 0 10px;padding-left:12px;border-left:3px solid #ff5a00}
h3{font-size:19px;margin:28px 0 8px}
p,ul,ol,table,blockquote,figure{margin:0 0 16px}
a{color:#c2410c}
img{max-width:100%;height:auto;border-radius:10px}
.hero{display:block;margin:0 0 28px;border:1px solid #e6e4df}
ul,ol{padding-left:24px}
li{margin-bottom:6px}
blockquote{margin-left:0;padding:4px 0 4px 16px;border-left:3px solid #e6e4df;color:#3a3a42}
.table-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:9px 12px 9px 0;border-bottom:1px solid #e6e4df;vertical-align:top}
th{font-weight:600}
blockquote[class^="pb-"]{border-radius:10px;padding:14px 18px}
blockquote[class^="pb-"] p:last-child,blockquote[class^="pb-"] ul:last-child{margin-bottom:0}
.pb-tldr,.pb-example{background:#fff7f1;border:1px solid #ffd9c2;border-left:4px solid #ff5a00}
.pb-tldr>p:first-child strong,.pb-example>p:first-child strong:first-child{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#c2410c}
.pb-who{background:none;border-left:3px solid #d4d2cc;border-radius:0;padding:2px 0 2px 14px}
.pb-tip{background:#effaf4;border-left:4px solid #1d8a52}
.pb-tip strong:first-child{color:#1d6b45}
.pb-warn{background:#fff7e8;border-left:4px solid #b7791f}
.pb-warn strong:first-child{color:#8a5a00}
.pb-flow{background:#f6f5f2;border:1px dashed #cfccc4;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px}
.pb-cta{background:#1d1d22;color:#fff;border:0}
.pb-cta a{color:#ffb98a;font-weight:600}
.author{margin:40px 0 0;padding:18px 20px;background:#f6f5f2;border-left:4px solid #ff5a00;border-radius:10px}
.author h2{margin:0 0 8px;padding:0;border:0;font-size:18px}
.faq{margin-top:40px}
.faq h3{margin:22px 0 6px;font-size:17px}
footer{max-width:760px;margin:0 auto;padding:16px 20px 40px;font-size:12px;color:#8a8a93;border-top:1px solid #e6e4df}
@media (max-width:480px){body{font-size:16px}h1{font-size:27px}h2{font-size:21px}main{padding-top:24px}}
@media print{body{font-size:12pt}.table-scroll{overflow:visible}a{color:inherit}}
"""


def style_playbook_blocks(body_html: str) -> str:
    """Add the pb-* classes, only for posts that carry a TL;DR (as the site does)."""
    def label_of(match: "re.Match[str]") -> str:
        return match.group(2).strip().rstrip(":").strip().lower()

    if not any(label_of(m) == "tl;dr" for m in _LABELLED_QUOTE.finditer(body_html)):
        return body_html

    def classify(match: "re.Match[str]") -> str:
        css = PLAYBOOK_CLASSES.get(label_of(match))
        return match.group(0) if css is None else f'<blockquote class="{css}">{match.group(1)}'

    styled = _LABELLED_QUOTE.sub(classify, body_html)
    return _TABLE.sub(lambda m: f'<div class="table-scroll">{m.group(0)}</div>', styled)


def strip_author_placeholder(md: str) -> str:
    return _FROM_AUTHOR_LINE.sub("", md or "")


def render(
    *,
    title: str,
    meta_title: Optional[str],
    meta_description: Optional[str],
    body_html: str,
    faqs: List[Dict[str, Any]],
    from_author_story: Optional[str],
    score: Optional[int],
    image: Optional[tuple] = None,           # (bytes, mime)
    image_alt: Optional[str] = None,
    exported_at: Optional[datetime] = None,
) -> str:
    esc = html.escape
    exported_at = exported_at or datetime.now(timezone.utc)
    page_title = meta_title or title

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light only">',
        f"<title>{esc(page_title)}</title>",
    ]
    if meta_description:
        parts.append(f'<meta name="description" content="{esc(meta_description)}">')
    parts += [f"<style>{CSS}</style>", "</head>", "<body>", "<main>"]

    # Most bodies carry their own "# Title"; add one only when they do not.
    if "<h1" not in body_html:
        parts.append(f"<h1>{esc(title)}</h1>")

    if image:
        content, mime = image
        encoded = base64.b64encode(content).decode("ascii")
        parts.append(f'<img class="hero" src="data:{esc(mime)};base64,{encoded}" '
                     f'alt="{esc(image_alt or "")}">')

    parts.append(f'<div class="body">{body_html}</div>')

    story = (from_author_story or "").strip()
    if story:
        paragraphs = "".join(f"<p>{esc(p.strip())}</p>"
                             for p in re.split(r"\n\s*\n", story) if p.strip())
        parts.append(f'<section class="author"><h2>From the author</h2>{paragraphs}</section>')

    answered = [f for f in faqs if (f.get("question") or "").strip()]
    if answered:
        parts.append('<section class="faq"><h2>Frequently asked questions</h2>')
        for faq in answered:
            parts.append(f"<h3>{esc(faq['question'])}</h3>")
            parts.append(f"<p>{esc(faq.get('answer') or '')}</p>")
        parts.append("</section>")

    parts.append("</main>")
    parts.append(
        "<footer>Exported from the Agentic AI Automation dashboard on "
        f"{exported_at.strftime('%d %b %Y, %H:%M UTC')}"
        + (f" · house score {score}/100" if score is not None else "")
        + "</footer>")
    parts += ["</body>", "</html>", ""]
    return "\n".join(parts)
