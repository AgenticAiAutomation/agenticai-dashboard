"""design_tokens.json -> the article stylesheet.

One stylesheet, two consumers: the dashboard preview and the public page both
inline exactly this output, so they cannot diverge. Every colour, size and
spacing value below is read from the token file; nothing is hard-coded here
except structure.

The output is inlined into <head>, so it has to stay under the 14 KB critical
budget from the work order. tests/blog_engine_test.py enforces that.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from typing import Any, Dict

TOKENS_PATH = os.path.join(os.path.dirname(__file__), "design_tokens.json")
CRITICAL_BUDGET_BYTES = 14 * 1024


@lru_cache(maxsize=1)
def tokens() -> Dict[str, Any]:
    with open(TOKENS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _vars(t: Dict[str, Any]) -> str:
    out = []
    for k, v in t["color"].items():
        if not k.startswith("$"):
            out.append(f"--c-{k}:{v}")
    for k, v in t["highlight"].items():
        if not k.startswith("$"):
            out.append(f"--hl-{k}-bg:{v['bg']};--hl-{k}-fg:{v['fg']}")
    for k, v in t["font"].items():
        if not k.startswith("$"):
            out.append(f"--f-{k}:{v}")
    for k, v in t["type"].items():
        if k.startswith("$") or k == "line":
            continue
        out.append(f"--t-{k}:{v}")
    for k, v in t["type"]["line"].items():
        out.append(f"--lh-{k}:{v}")
    for k, v in t["space"].items():
        if not k.startswith("$"):
            out.append(f"--s{k}:{v}")
    for k, v in t["radius"].items():
        out.append(f"--r{k}:{v}")
    for k, v in t["shadow"].items():
        out.append(f"--sh{k}:{v}")
    for k, v in t["layout"].items():
        out.append(f"--l-{k}:{v}")
    m = t["motion"]
    out.append(f"--m-rise:{m['reveal_rise']};--m-ms:{m['reveal_ms']}ms;--m-ease:{m['ease']}")
    return ".page-blog-v2{" + ";".join(out) + "}"


# The structural rules. Written compact on purpose: this is inlined on every
# article. Each selector is prefixed with .page-blog-v2 by build() so nothing
# here can leak into the site's own components on a legacy page.
CRITICAL_RULES = r"""
.v2-layout{padding:var(--s2) 0 var(--s7)}
.v2-body{max-width:var(--l-column);margin:0 auto;padding:0 var(--l-gutter);font:400 var(--t-body)/var(--lh-body) var(--f-body);color:var(--c-ink)}
.v2-body>*{margin-block:0 var(--s5)}
.v2-body>p{max-width:var(--t-measure)}
.v2-body p.lead{font-size:var(--t-lead);line-height:var(--lh-lead);color:var(--c-ink);letter-spacing:-.005em}
.v2-body h2,.v2-body h3,.v2-body h4{font-family:var(--f-display);font-weight:800;line-height:var(--lh-tight);letter-spacing:-.02em;color:var(--c-ink);scroll-margin-top:84px;text-wrap:balance}
.v2-body h2{font-size:var(--t-h2);margin-top:var(--s7);position:relative}
.v2-body h3{font-size:var(--t-h3);margin-top:var(--s6)}
.v2-body h4{font-size:var(--t-h4);margin-top:var(--s5)}
.v2-body h2.grad{background:linear-gradient(92deg,var(--c-ink) 0%,var(--c-brand-hi) 60%,var(--c-accent) 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.v2-body a{color:var(--c-brand-hi);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.v2-body a:hover{color:var(--c-accent)}
.v2-body a:focus-visible,.v2-body button:focus-visible,.v2-body summary:focus-visible,.v2-body [tabindex]:focus-visible{outline:2px solid var(--c-accent);outline-offset:3px;border-radius:2px}
.v2-body strong{color:var(--c-ink);font-weight:600}
.v2-body code{font:500 .92em var(--f-mono);background:var(--c-surface-raised);border:1px solid var(--c-rule);border-radius:var(--r1);padding:.08em .35em}
.v2-body mark.hl{padding:.02em .28em;border-radius:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.v2-body .hl-amber{background:var(--hl-amber-bg);color:var(--hl-amber-fg)}
.v2-body .hl-mint{background:var(--hl-mint-bg);color:var(--hl-mint-fg)}
.v2-body .hl-sky{background:var(--hl-sky-bg);color:var(--hl-sky-fg)}
.v2-body .hl-rose{background:var(--hl-rose-bg);color:var(--hl-rose-fg)}
.v2-body .em-brand{color:var(--c-brand-hi)}.v2-body .em-accent{color:var(--c-accent)}.v2-body .em-positive{color:var(--c-signal-positive)}.v2-body .em-warning{color:var(--c-signal-warning)}
.b-label{font:600 var(--t-small) var(--f-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--c-ink-muted);margin:0 0 var(--s3)}
.b-full{max-width:none;margin-left:calc(-1*var(--l-gutter));margin-right:calc(-1*var(--l-gutter))}
.b-breakout{width:var(--l-breakout);max-width:var(--l-breakout);margin-left:50%;transform:translateX(-50%)}
.v2-body figure{margin-block:var(--s6)}
.v2-body figcaption{font:400 var(--t-small)/1.5 var(--f-body);color:var(--c-ink-muted);margin-top:var(--s3)}
.v2-body figcaption .credit{display:block;font-family:var(--f-mono);font-size:.85em;color:var(--c-ink-faint);margin-top:2px}
.b-image img,.b-gallery img,.b-compare img{display:block;width:100%;height:auto;border-radius:var(--r2);background-size:cover;background-position:center}
.b-image.b-inset img{box-shadow:var(--sh2)}
.b-takeaways{border:1px solid var(--c-rule-2);border-left:3px solid var(--c-accent);border-radius:var(--r2);padding:var(--s4) var(--s5);background:var(--c-surface-raised)}
.b-takeaways ul{margin:0;padding-left:1.1em}.b-takeaways li{margin:0 0 var(--s2)}.b-takeaways li::marker{color:var(--c-accent)}
.b-toc{max-width:var(--l-column);margin:0 auto var(--s5);padding:0 var(--l-gutter)}
.b-toc details{border:1px solid var(--c-rule-2);border-radius:var(--r2);padding:var(--s3) var(--s4);background:var(--c-surface-raised)}
.b-toc summary{cursor:pointer;font:600 var(--t-small) var(--f-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--c-ink-muted)}
.b-toc ol{margin:var(--s3) 0 0;padding-left:1.2em;font-size:var(--t-small);line-height:1.5}.b-toc li{margin:0 0 6px}.b-toc li.l3{padding-left:1em;list-style:none}
.b-toc a{color:var(--c-ink);text-decoration:none}.b-toc a:hover,.b-toc a.on{color:var(--c-accent)}
@media(min-width:1100px){.b-toc{position:sticky;top:84px;float:left;width:220px;margin-left:calc(50% - 34ch - 250px);padding:0}.b-toc details{background:transparent;border:0;padding:0}}
.readbar{position:fixed;left:0;top:0;height:3px;width:100%;z-index:50;pointer-events:none}
.readbar .fill{height:100%;width:100%;background:linear-gradient(90deg,var(--c-brand),var(--c-accent));transform-origin:left;transform:scaleX(0)}
@supports(animation-timeline:scroll()){.readbar .fill{animation:v2read linear both;animation-timeline:scroll(root)}@keyframes v2read{from{transform:scaleX(0)}to{transform:scaleX(1)}}}
html.js [data-reveal]{opacity:0;transform:translateY(var(--m-rise))}
html.js [data-reveal].in{opacity:1;transform:none;transition:opacity var(--m-ms) var(--m-ease),transform var(--m-ms) var(--m-ease)}
.vh{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(prefers-reduced-motion:reduce){.page-blog-v2 *,.page-blog-v2 *::before,.page-blog-v2 *::after{animation:none!important;transition:none!important}html.js [data-reveal]{opacity:1;transform:none}.b-flow .pulse{display:none}.readbar{display:none}}
@media(max-width:1099px){.b-breakout{width:auto;max-width:none;margin-left:calc(-1*var(--l-gutter));margin-right:calc(-1*var(--l-gutter));transform:none}}
"""

# Below-the-fold block styles: linked as a content-hashed file so every
# article shares one cached copy, and the inline part stays small.
DEFERRED_RULES = r"""
.b-gallery .grid{display:grid;gap:var(--s3);grid-template-columns:repeat(2,1fr)}
.b-gallery.n3 .grid{grid-template-columns:repeat(3,1fr)}.b-gallery.n4 .grid{grid-template-columns:repeat(2,1fr)}
.b-gallery .grid figure{margin-block:0}
@media(max-width:600px){.b-gallery .grid,.b-gallery.n3 .grid{grid-template-columns:1fr}}
.b-compare{position:relative;display:grid;grid-template-columns:1fr 1fr;gap:var(--s2)}
.b-compare .pane{position:relative}
.b-compare .b-tag{position:absolute;top:var(--s2);left:var(--s2);font:600 var(--t-small) var(--f-mono);background:var(--c-surface);color:var(--c-ink);padding:2px 8px;border-radius:var(--r1);z-index:1}
.b-compare figcaption{grid-column:1/-1}
.b-video video,.b-video .yt{display:block;width:100%;height:auto;border-radius:var(--r2);background:var(--c-surface-raised)}
.b-video .yt{position:relative;overflow:hidden}
.b-video .yt img{width:100%;height:100%;object-fit:cover;display:block}
.b-video .yt .play{position:absolute;inset:50% auto auto 50%;width:72px;height:72px;transform:translate(-50%,-50%);border-radius:50%;background:var(--c-brand);box-shadow:var(--sh3)}
.b-video .yt .play::after{content:"";position:absolute;left:29px;top:22px;border-style:solid;border-width:14px 0 14px 22px;border-color:transparent transparent transparent var(--c-on-bright)}
.b-table .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--c-rule);border-radius:var(--r2);background:var(--c-surface-raised)}
.b-table table{width:100%;border-collapse:collapse;font-size:var(--t-small);font-variant-numeric:tabular-nums}
.b-table caption{caption-side:top;text-align:left;font:600 var(--t-body) var(--f-display);color:var(--c-ink);padding:var(--s3) var(--s4)}
.b-table th,.b-table td{padding:var(--s3) var(--s4);border-top:1px solid var(--c-rule);text-align:left;vertical-align:top}
.b-table th{font:600 var(--t-small) var(--f-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--c-ink-muted);background:var(--c-surface-raised-2)}
.b-table .ta-right{text-align:right}.b-table .ta-center{text-align:center}
.b-table tbody tr:hover td{background:rgba(250,247,241,.03)}
@media(max-width:600px){.b-table.m-stack thead{display:none}.b-table.m-stack tr{display:block;border-top:1px solid var(--c-rule-2)}.b-table.m-stack td{display:grid;grid-template-columns:40% 1fr;border-top:0;text-align:left}.b-table.m-stack td::before{content:attr(data-label);font:600 var(--t-small) var(--f-mono);color:var(--c-ink-muted)}}
.b-list{padding-left:1.25em}.b-list li{margin:0 0 var(--s2)}.b-list li::marker{color:var(--c-brand-hi)}
.b-list.s-checklist{list-style:none;padding:0}.b-list.s-checklist li{display:flex;gap:var(--s3);align-items:flex-start}
.b-list .chk{flex:none;width:18px;height:18px;margin-top:.2em;border:1.5px solid var(--c-rule-3);border-radius:4px}
.b-list .chk.on{background:var(--c-signal-positive);border-color:var(--c-signal-positive)}
.b-list li.done{color:var(--c-ink-muted)}
.b-steps ol{list-style:none;margin:0;padding:0;counter-reset:s}
.b-steps li{display:grid;grid-template-columns:auto 1fr;gap:var(--s4);padding:var(--s4) 0;border-top:1px solid var(--c-rule)}
.b-steps .b-n{font:800 var(--t-stat)/1 var(--f-display);color:var(--c-brand);min-width:1.4em;letter-spacing:-.04em}
.b-steps .st{font:700 var(--t-h4) var(--f-display);margin:0 0 var(--s2);color:var(--c-ink)}
.b-steps li p{margin:0 0 var(--s2)}.b-steps li figure{margin:var(--s3) 0 0}
.b-callout{border-radius:var(--r2);padding:var(--s4) var(--s5);background:var(--c-surface-raised);border-left:3px solid var(--c-ink-muted)}
.b-callout p:last-child{margin:0}
.b-callout.k-tip{border-left-color:var(--c-signal-positive)}.b-callout.k-tip .b-label{color:var(--c-signal-positive)}
.b-callout.k-warning{border-left-color:var(--c-signal-warning)}.b-callout.k-warning .b-label{color:var(--c-signal-warning)}
.b-callout.k-result{border-left-color:var(--c-accent);background:linear-gradient(90deg,rgba(255,212,0,.08),transparent 60%)}.b-callout.k-result .b-label{color:var(--c-accent)}
.b-quote{border-left:3px solid var(--c-brand);padding-left:var(--s5)}
.b-quote blockquote{margin:0}.b-quote p{font:500 var(--t-lead)/var(--lh-lead) var(--f-display);letter-spacing:-.01em;color:var(--c-ink);margin:0 0 var(--s3)}
.b-quote cite{font-style:normal;font:600 var(--t-small) var(--f-mono);color:var(--c-ink)}
.b-quote cite span{display:block;font-weight:400;color:var(--c-ink-muted)}
.b-code{border:1px solid var(--c-rule);border-radius:var(--r2);overflow:hidden;background:var(--c-surface-raised)}
.b-code figcaption{display:flex;gap:var(--s3);align-items:center;margin:0;padding:var(--s2) var(--s4);border-bottom:1px solid var(--c-rule);font:400 var(--t-small) var(--f-mono)}
.b-code .lang{color:var(--c-accent);text-transform:uppercase;letter-spacing:.1em;font-weight:600}
.b-code .copy{margin-left:auto;font:600 12px var(--f-mono);color:var(--c-ink);background:transparent;border:1px solid var(--c-rule-2);border-radius:var(--r1);padding:3px 10px;cursor:pointer}
.b-code pre{margin:0;padding:var(--s4);overflow-x:auto;font:400 var(--t-small)/1.6 var(--f-mono);color:var(--c-ink)}
.b-code pre code{background:none;border:0;padding:0;font-size:inherit}
.b-stats{display:grid;gap:var(--s4);grid-template-columns:repeat(auto-fit,minmax(140px,1fr));padding:var(--s5) 0;border-top:1px solid var(--c-rule-2);border-bottom:1px solid var(--c-rule-2)}
.b-stats .b-stat{background:var(--c-surface-raised);border-radius:var(--r2);padding:var(--s4) var(--s4) var(--s3)}
.b-stats .num{font:800 var(--t-stat)/1 var(--f-display);letter-spacing:-.04em;color:var(--c-ink);margin:0;font-variant-numeric:tabular-nums}
.b-stats .num .pre,.b-stats .num .suf{font-size:.5em;color:var(--c-brand-hi);vertical-align:.35em}
.b-stats .b-lbl{font:400 var(--t-small)/1.4 var(--f-body);color:var(--c-ink-muted);margin:var(--s2) 0 0}
.b-chart svg,.b-flow svg{display:block;width:100%;height:auto;aspect-ratio:16/9}
.b-chart .k-donut{aspect-ratio:8/3}
.b-chart .grid{stroke:var(--c-rule-2);stroke-width:1}
.b-chart .b-tick,.b-chart .b-lbl,.b-chart .val{font:400 12px var(--f-mono);fill:var(--c-ink-muted)}
.b-chart .val{fill:var(--c-ink);font-weight:600}
.b-chart .s0{fill:var(--c-brand);stroke:var(--c-brand)}.b-chart .s1{fill:var(--c-accent);stroke:var(--c-accent)}.b-chart .s2{fill:var(--c-signal-positive);stroke:var(--c-signal-positive)}.b-chart .s3{fill:var(--c-ink-muted);stroke:var(--c-ink-muted)}
.b-chart .line{fill:none;stroke-width:3;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:0}
.b-chart .arc{fill:none;stroke-width:28;transform:rotate(-90deg);transform-origin:120px 120px}
.b-chart .b-bar{transform-origin:bottom}
.b-chart-legend{display:flex;flex-wrap:wrap;gap:var(--s2) var(--s4);list-style:none;margin:var(--s3) 0 0;padding:0;font:400 var(--t-small) var(--f-mono);color:var(--c-ink-muted)}
.b-chart .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.b-chart-legend .s0{background:var(--c-brand)}.b-chart-legend .s1{background:var(--c-accent)}.b-chart-legend .s2{background:var(--c-signal-positive)}.b-chart-legend .s3{background:var(--c-ink-muted)}
.b-chart .src{font:400 var(--t-small) var(--f-mono);color:var(--c-ink-faint);margin:var(--s2) 0 0}
.b-flow .scroll{overflow-x:auto}.b-flow svg{min-width:520px;aspect-ratio:auto}
.b-flow .rail{stroke:var(--c-rule-3);stroke-width:2;fill:none}
.b-flow .arrow{stroke:var(--c-ink-muted);stroke-width:2;fill:none;stroke-linecap:round;stroke-linejoin:round}
.b-flow .node rect{fill:var(--c-surface-raised);stroke:var(--c-rule-3);stroke-width:1.5}
.b-flow .node.k-bot rect{stroke:var(--c-brand)}.b-flow .node.k-result rect{stroke:var(--c-signal-positive)}.b-flow .node.k-human rect{stroke:var(--c-accent)}.b-flow .node.k-decision rect{stroke:var(--c-signal-warning)}
.b-flow .nl{font:600 14px var(--f-display);fill:var(--c-ink)}.b-flow .ns{font:400 11px var(--f-mono);fill:var(--c-ink-muted)}
.b-flow .pulse{fill:var(--c-accent);offset-rotate:0deg;animation:v2flow 3.2s linear infinite}
@keyframes v2flow{from{offset-distance:0%}to{offset-distance:100%}}
.b-faq h2{margin-top:var(--s7)}
.b-faq details{border-top:1px solid var(--c-rule-2);padding:var(--s3) 0}.b-faq details:last-child{border-bottom:1px solid var(--c-rule-2)}
.b-faq summary{cursor:pointer;font:600 var(--t-body) var(--f-display);color:var(--c-ink);list-style:none;display:flex;justify-content:space-between;gap:var(--s3);padding:var(--s2) 0}
.b-faq summary::-webkit-details-marker{display:none}
.b-faq summary::after{content:"+";font:400 1.4em/1 var(--f-mono);color:var(--c-brand-hi);flex:none}
.b-faq details[open] summary::after{content:"−"}
.b-faq details>div{padding:0 0 var(--s3);color:var(--c-ink-muted)}.b-faq details>div p{margin:0}
.b-cta{border:1px solid var(--c-rule-2);border-radius:var(--r3);padding:var(--s5) var(--s6);background:radial-gradient(120% 140% at 0% 0%,rgba(255,90,0,.14),transparent 55%),var(--c-surface-raised);text-align:left}
.b-cta .h{font:800 var(--t-h3)/var(--lh-tight) var(--f-display);letter-spacing:-.02em;margin:0 0 var(--s3);color:var(--c-ink)}
.b-cta p{margin:0 0 var(--s4);color:var(--c-ink-muted)}
.b-divider{border:0;height:1px;background:var(--c-rule-2);margin:var(--s7) auto;max-width:var(--t-measure)}
.b-divider.s-dots{background:none;height:auto;text-align:center;color:var(--c-ink-faint);letter-spacing:.8em}.b-divider.s-dots::before{content:"···"}
.b-divider.s-glyph{background:none;height:auto;text-align:center;color:var(--c-brand)}.b-divider.s-glyph::before{content:"◆";font-size:.7em}
.b-embed{display:block;border:1px solid var(--c-rule-2);border-radius:var(--r2);padding:var(--s4) var(--s5);background:var(--c-surface-raised);text-decoration:none!important;color:var(--c-ink)}
.b-embed .prov{font:600 var(--t-small) var(--f-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--c-ink-muted)}
.b-embed .t{font:600 var(--t-body) var(--f-display);margin:var(--s2) 0}.b-embed p{margin:0 0 var(--s2);color:var(--c-ink-muted)}
.b-embed .b-open{font:600 var(--t-small) var(--f-mono);color:var(--c-brand-hi)}
.b-legacy h2,.b-legacy h3{font-family:var(--f-display)}
.b-legacy img{max-width:100%;height:auto;border-radius:var(--r2)}
.b-legacy table{width:100%;border-collapse:collapse;font-size:var(--t-small)}.b-legacy td,.b-legacy th{border-top:1px solid var(--c-rule);padding:var(--s2) var(--s3);text-align:left}
.b-author{display:flex;gap:var(--s4);margin:var(--s7) 0 0;padding:var(--s5);border:1px solid var(--c-rule-2);border-radius:var(--r2);background:var(--c-surface-raised)}
.b-author img{width:72px;height:72px;border-radius:50%;flex:none;object-fit:cover}
.b-author .b-n{font:700 var(--t-body) var(--f-display);margin:0;color:var(--c-ink)}.b-author .t{font:400 var(--t-small) var(--f-mono);color:var(--c-ink-muted);margin:2px 0 var(--s2)}
.b-author .b-creds{margin:var(--s2) 0;padding-left:1.1em;font-size:var(--t-small);color:var(--c-ink-muted)}.b-author .links a{margin-right:var(--s3);font:600 var(--t-small) var(--f-mono)}
"""



SCOPE = ".page-blog-v2"


def _scope_selector_list(selectors: str) -> str:
    parts = []
    for sel in selectors.split(","):
        sel = sel.strip()
        if not sel:
            continue
        if sel.startswith(SCOPE) or sel.startswith("html.js"):
            parts.append(sel)
        else:
            parts.append(f"{SCOPE} {sel}")
    return ",".join(parts)


def _prefix(rules: str) -> str:
    """Scope every selector under .page-blog-v2 so a legacy page is untouched
    even if this sheet were ever loaded there. Walks the braces properly, so
    several rules on one line and rules nested in @media both get scoped;
    @keyframes bodies are left alone."""
    out = []
    i, n = 0, len(rules)
    while i < n:
        j = rules.find("{", i)
        if j == -1:
            break
        head = rules[i:j].strip()
        if not head:
            i = j + 1
            continue
        # Find the matching close brace for this block.
        depth, k = 1, j + 1
        while k < n and depth:
            if rules[k] == "{":
                depth += 1
            elif rules[k] == "}":
                depth -= 1
            k += 1
        inner = rules[j + 1:k - 1]
        if head.startswith("@keyframes"):
            out.append(f"{head}{{{inner}}}")
        elif head.startswith("@"):
            out.append(f"{head}{{{_prefix(inner)}}}")
        else:
            out.append(f"{_scope_selector_list(head)}{{{inner}}}")
        i = k
    return "".join(out)


def _minify(css: str) -> str:
    css = re.sub(r"\s*([{};:,>])\s*", lambda m: m.group(1), css)
    return css.replace(";}", "}")


@lru_cache(maxsize=1)
def build_critical() -> str:
    """Tokens + above-the-fold rules. Inlined in <head> of every article."""
    return _minify(_vars(tokens()) + _prefix(CRITICAL_RULES))


@lru_cache(maxsize=1)
def build_deferred() -> str:
    """Block styles below the fold. Written once as a content-hashed file."""
    return _minify(_prefix(DEFERRED_RULES))


def build() -> str:
    """Everything, for the editor preview."""
    return build_critical() + build_deferred()


def deferred_filename() -> str:
    h = hashlib.sha256(build_deferred().encode("utf-8")).hexdigest()[:10]
    return f"blog-engine.{h}.css"


def content_hash() -> str:
    return hashlib.sha256(build().encode("utf-8")).hexdigest()[:10]


def critical_size_bytes() -> int:
    return len(build_critical().encode("utf-8"))


def size_bytes() -> int:
    return len(build().encode("utf-8"))
