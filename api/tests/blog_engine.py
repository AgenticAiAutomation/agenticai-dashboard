"""Blog Visual Engine — offline test suite.

Pure functions over the fixture: no database, no network, no server. Runs in
well under a second, which is the point — every invariant the work order
names as a hard rule is checked here on every change.

Usage:
    python -m tests.blog_engine
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blog_engine import css, sanitize, seo, validate  # noqa: E402
from app.blog_engine.render import (ArticleMeta, RenderResult, render_article,  # noqa: E402
                                    render_page)
from app.blog_engine.schema import BLOCK_TYPES, BlockError, parse_blocks  # noqa: E402
from scripts.render_fixture import load_fixture  # noqa: E402

passed, failed = [], []


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}   {detail}")


def section(title):
    print(f"\n{title}\n" + "-" * 60)


# ---------------------------------------------------------------------------
def _srgb(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


meta, blocks = load_fixture()
result = render_article(blocks)
page, _ = render_page(blocks, meta)

section("1. Schema")
check("fixture parses", len(blocks) == 33)
check("all 21 block types are exercised by the fixture",
      set(b.type for b in blocks) == set(BLOCK_TYPES), set(BLOCK_TYPES) - set(b.type for b in blocks))
bad = [
    ("alt repeats filename", [{"id": "blk_a100", "type": "image", "attrs": {"src": "/x/queue-dash.jpg", "alt": "queue dash", "width": 1, "height": 1}}]),
    ("table without caption", [{"id": "blk_a200", "type": "table", "attrs": {"caption": " "}, "content": [[{"text": "a"}]]}]),
    ("gradient on h3", [{"id": "blk_a300", "type": "heading", "attrs": {"level": 3, "gradient": True}, "content": "T"}]),
    ("javascript: href", [{"id": "blk_a400", "type": "paragraph", "content": [{"text": "a", "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}]}]}]),
    ("hex colour instead of token", [{"id": "blk_a500", "type": "paragraph", "content": [{"text": "a", "marks": [{"type": "highlight", "attrs": {"token": "#F59E0B"}}]}]}]),
    ("duplicate ids", [{"id": "blk_a600", "type": "divider"}, {"id": "blk_a600", "type": "divider"}]),
    ("video without description", [{"id": "blk_a700", "type": "video", "attrs": {"kind": "youtube", "youtube_id": "dQw4w9WgXcQ", "poster": "/p.jpg", "title": "t", "description": " ", "upload_date": "2026-09-18", "duration": "PT1M"}}]),
    ("key_takeaways with 2 bullets", [{"id": "blk_a800", "type": "key_takeaways", "content": ["a", "b"]}]),
    ("unknown block type", [{"id": "blk_a900", "type": "carousel"}]),
    ("ragged table", [{"id": "blk_b100", "type": "table", "attrs": {"caption": "c"}, "content": [["a", "b"], ["c"]]}]),
    ("embed from unknown host", [{"id": "blk_b200", "type": "embed", "attrs": {"provider": "x", "url": "https://evil.example/x"}}]),
    ("alt over 125 chars", [{"id": "blk_b300", "type": "image", "attrs": {"src": "/x/a.jpg", "alt": "x" * 126, "width": 1, "height": 1}}]),
]
for name, raw in bad:
    try:
        parse_blocks(raw)
        check(f"rejects: {name}", False, "parsed without error")
    except BlockError as exc:
        check(f"rejects: {name}", True)
        if "blk_" in str(exc) or "duplicate" in str(exc):
            pass
        else:
            check(f"error names the block: {name}", False, str(exc))

section("2. Design tokens")
t = css.tokens()
for name, pair in t["highlight"].items():
    if name.startswith("$"):
        continue
    ratio = contrast(pair["bg"], pair["fg"])
    check(f"highlight.{name} contrast >= 4.5:1 ({ratio:.1f})", ratio >= 4.5)
check("ink on surface >= 7:1 (body text)", contrast(t["color"]["ink"], t["color"]["surface"]) >= 7)
check("ink-muted on surface >= 4.5:1", contrast(t["color"]["ink-muted"], t["color"]["surface"]) >= 4.5)
check("no hex literal in a highlight token name", all(not k.startswith("#") for k in t["highlight"]))
check("two font families above the fold", len([k for k in t["font"] if not k.startswith("$")]) == 3)

section("3. Stylesheet")
crit = css.build_critical()
check(f"critical css under 14 KB ({css.critical_size_bytes()} B)", css.critical_size_bytes() <= css.CRITICAL_BUDGET_BYTES)
check(f"total css under 20 KB hard fail ({css.size_bytes()} B)", css.size_bytes() <= 20 * 1024)


def unscoped(s):
    s = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", s)
    s = re.sub(r"@(media|supports)[^{]*\{", "", s)
    out = []
    for h in re.findall(r"([^{}]+)\{", s):
        for part in h.split(","):
            part = part.strip().lstrip("}")
            if part and not (part.startswith(".page-blog-v2") or part.startswith("html.js")):
                out.append(part)
    return out


check("every critical selector is scoped to .page-blog-v2", not unscoped(crit), unscoped(crit)[:3])
check("every deferred selector is scoped to .page-blog-v2", not unscoped(css.build_deferred()), unscoped(css.build_deferred())[:3])
check("no hex colours outside the token block", not re.findall(r"#[0-9a-fA-F]{3,6}\b", css.build().split("}", 1)[1]))
check("reduced-motion kills animation and transition", "prefers-reduced-motion:reduce" in crit and "animation:none!important" in crit)
check("only transform/opacity animate",
      not re.search(r"transition:[^}]*\b(width|height|top|left|margin)\b", css.build()))
check("deferred filename is content-hashed", re.match(r"^blog-engine\.[0-9a-f]{10}\.css$", css.deferred_filename()) is not None)

section("4. Renderer invariants")
h = page
check("exactly one <h1>", h.count("<h1") == 1)
check("heading ids unique", len(re.findall(r'<h[234] id="', h)) == len(set(re.findall(r'<h[234] id="([^"]+)"', h))))
imgs = re.findall(r"<img [^>]*>", h)
check("every <img> has alt", all('alt="' in i for i in imgs))
check("every non-legacy <img> has width and height",
      all('width="' in i and 'height="' in i for i in re.findall(r"<img [^>]*>", h.split('class="b-legacy"')[0])))
check("one fetchpriority=high (the hero), the rest lazy", h.count('fetchpriority="high"') == 1 and h.count('loading="lazy"') >= 6)
check("every visible table has a caption", h.count("<table>") + h.count('<table data-sortable="1">') == h.count("<caption>") - 2)
check("no <iframe> (video is a facade)", "<iframe" not in h)
check("no inline event handlers", not re.search(r"\son[a-z]+=", h))
check("no javascript: urls", "javascript:" not in h.lower())
check("first three blocks carry no reveal hook", not re.search(r'<[^>]*data-reveal[^>]*data-block="blk_(kt01|p001|p002)"', h))
check("later blocks carry the reveal hook", re.search(r'<[^>]*data-reveal[^>]*data-block="blk_h001"', h) is not None)
check("dividers never animate", not re.search(r'<hr[^>]*data-reveal', h))
check("gradient only on h2", not re.search(r"<h[34][^>]*grad", h))
body_html = h.split('<article class="v2-body"')[1].split("</article>")[0]
check("external links in the body get rel=noopener",
      all("noopener" in a for a in re.findall(r'<a [^>]*href="https?://(?!agenticaiautomation\.co)[^"]*"[^>]*>', body_html)))
check("every target=_blank anywhere carries noopener",
      all("noopener" in a for a in re.findall(r'<a [^>]*target="_blank"[^>]*>', h)))
check("internal links have no target=_blank", not re.search(r'<a [^>]*href="/[^"]*"[^>]*target=', h))
check("rupee sign survives", "₹" in h)
check("word count is sane", 800 < result.word_count < 1000, result.word_count)
check("reading minutes derived from words", result.reading_minutes == max(1, -(-result.word_count // 220)))
check("chrome present (nav, footer socials, preferred source)",
      'class="navlinks"' in h and 'class="fsocials"' in h and "google-add-preferred-source-btn" in h)
check("CSP present, hashes the inline GA script", 'http-equiv="Content-Security-Policy"' in h and "'sha256-" in h)
scripts = set(re.findall(r'<script[^>]+src="([^"]+)"', h))
check("no third-party script beyond GA and Google news", scripts <= {
    "https://www.googletagmanager.com/gtag/js?id=G-76LF2H3EL4",
    "https://news.google.com/swg/js/v1/publisher.js", "/static/assets/js/site.js"}, scripts)
check("deferred stylesheet linked by hash", f'/static/blog/engine/{css.deferred_filename()}' in h)
check("generator meta names engine and chrome version", 'name="generator" content="blog-engine' in h)

section("5. Determinism")
page2, _ = render_page(blocks, meta)
check("rendering twice is byte-identical", page == page2)
check("re-parsing the fixture gives identical blocks", parse_blocks(json.load(open(load_fixture.__globals__["FIXTURE"], encoding="utf-8"))["blocks"]) == blocks)

section("6. Sanitiser (legacy_html)")
cases = [
    ("<p>ok <strong>b</strong></p><script>alert(1)</script>", lambda o: "<script" not in o and "<strong>b</strong>" in o),
    ('<img src="/a.jpg" onerror="x()">', lambda o: "onerror" not in o and 'alt=""' in o and 'loading="lazy"' in o),
    ('<img src="javascript:x">', lambda o: "<img" not in o),
    ('<a href="javascript:x">l</a>', lambda o: "javascript" not in o),
    ('<a href="https://x.com/">l</a>', lambda o: 'rel="noopener"' in o),
    ('<p style="color:red" class="x">t</p>', lambda o: "style=" not in o and "class=" not in o),
    ('<iframe src="https://evil"></iframe><p>t</p>', lambda o: "<iframe" not in o),
    ('<svg onload="x()"></svg>', lambda o: "<svg" not in o),
    ('<code class="language-python">x</code>', lambda o: 'class="language-python"' in o),
    ('<code class="evil">x</code>', lambda o: "evil" not in o),
    ("<!-- c --><p>t</p>", lambda o: "<!--" not in o),
]
for raw, ok in cases:
    check(f"sanitise: {raw[:40]}", ok(sanitize.clean(raw)), sanitize.clean(raw)[:80])

section("7. JSON-LD")
docs = seo.build(meta, result)
types = [d["@type"] for d in docs]
check("BlogPosting, BreadcrumbList, FAQPage, HowTo, VideoObject, Quotation",
      {"BlogPosting", "BreadcrumbList", "FAQPage", "HowTo", "VideoObject", "Quotation"} <= set(types), types)
faq = next(d for d in docs if d["@type"] == "FAQPage")
check("FAQPage questions match the rendered accordion",
      [q["name"] for q in faq["mainEntity"]] == [q for q, _ in result.faqs] and len(result.faqs) == h.count('<details class="faq"'))
howto = next(d for d in docs if d["@type"] == "HowTo")
check("HowTo steps anchor into the page", all(s["url"].split("#")[1] in h for s in howto["step"]))
video = next(d for d in docs if d["@type"] == "VideoObject")
check("VideoObject has name/description/thumbnail/uploadDate/duration",
      all(k in video for k in ("name", "description", "thumbnailUrl", "uploadDate", "duration")))
post = next(d for d in docs if d["@type"] == "BlogPosting")
check("BlogPosting wordCount equals renderer's", post["wordCount"] == result.word_count)
check("every JSON-LD doc serialises", all(json.dumps(d) for d in docs))
check("no HowTo for a 2-step block",
      not seo.how_tos(meta, RenderResult(**{**result.__dict__, "steps": [parse_blocks([{"id": "blk_s002", "type": "steps", "content": [{"title": "a"}, {"title": "b"}]}])[0]]})))

section("8. Validators")
v = validate.validate_article(blocks, meta, result)
check("fixture has no blocking violations", not validate.blocking(v), [str(x) for x in validate.blocking(v)])
check("violations sorted blocks-first", [x.level for x in v] == sorted([x.level for x in v], key=lambda l: 0 if l == "block" else 1))

# Effect limits.
many_grad = parse_blocks([{"id": f"blk_g00{i}", "type": "heading", "attrs": {"level": 2, "gradient": True}, "content": f"H{i}"} for i in range(3)])
r2 = render_article(many_grad)
check("3 gradient headlines -> warning", any(x.rule == "effect.gradient_headline" for x in validate.validate_article(many_grad, meta, r2)))
hl = [{"id": f"blk_m00{i}", "type": "paragraph", "content": [{"text": "x", "marks": [{"type": "highlight", "attrs": {"token": "amber"}}]}]} for i in range(5)]
r3 = render_article(parse_blocks(hl))
check("5 marker highlights -> warning", any(x.rule == "effect.marker_highlight" for x in validate.validate_article(parse_blocks(hl), meta, r3)))
two_leads = parse_blocks([{"id": "blk_l100", "type": "paragraph", "attrs": {"variant": "lead"}, "content": "a"},
                          {"id": "blk_l200", "type": "paragraph", "attrs": {"variant": "lead"}, "content": "b"}])
check("two leads in one section -> warning", any(x.rule == "effect.lead_paragraph" for x in validate.validate_article(two_leads, meta, render_article(two_leads))))

# Rhythm.
wall = parse_blocks([{"id": f"blk_w00{i}", "type": "paragraph", "content": " ".join(["word"] * 90)} for i in range(4)])
rw = render_article(wall)
vw = validate.validate_article(wall, meta, rw)
check("360 words with no visual -> wall_of_text warning", any(x.rule == "rhythm.wall_of_text" for x in vw))
check("no key_takeaways -> warning", any(x.rule == "rhythm.key_takeaways" for x in vw))
check("no faq -> warning", any(x.rule == "rhythm.faq" for x in vw))

# Structure.
skip = parse_blocks([{"id": "blk_k100", "type": "heading", "attrs": {"level": 2}, "content": "a"},
                     {"id": "blk_k200", "type": "heading", "attrs": {"level": 4}, "content": "b"}])
check("h2 -> h4 skip is blocking", any(x.rule == "structure.heading_skip" and x.level == "block"
                                        for x in validate.validate_article(skip, meta, render_article(skip))))
thin = parse_blocks([{"id": "blk_t100", "type": "image", "attrs": {"src": "/x/a.jpg", "alt": "the dashboard", "width": 1, "height": 1}}])
check("two-word alt is blocking", any(x.rule == "image.alt_quality" and x.level == "block"
                                      for x in validate.validate_article(thin, meta, render_article(thin))))

# Meta.
bad_meta = ArticleMeta(slug="The_Slug", title="t", meta_description="short")
vm = validate.validate_article(blocks, bad_meta, result)
check("bad slug is blocking", any(x.rule == "meta.slug" and x.level == "block" for x in vm))
check("short meta description is blocking", any(x.rule == "meta.description_length" and x.level == "block" for x in vm))

print("\n" + "=" * 62)
print(f"  {len(passed)} passed, {len(failed)} failed")
print("=" * 62)
sys.exit(1 if failed else 0)
