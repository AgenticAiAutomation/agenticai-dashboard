"""Charts and process flows as inline SVG. Zero JavaScript.

Every graphic carries a <title>, a <desc> and a visually-hidden data table or
list, so the numbers are in the DOM for screen readers, for search engines
and for anyone with CSS off. Draw-in and the flow pulse are CSS animations on
stroke-dashoffset / offset-distance, which the reduced-motion rule switches
off in one media query — SMIL <animate> cannot be disabled that way, which
is why it is not used.

Dimensions come from a viewBox and the CSS reserves the aspect ratio, so the
box exists before paint and contributes nothing to CLS.
"""
from __future__ import annotations

import math
from typing import List

from app.blog_engine.inline import esc
from app.blog_engine.schema import ChartAttrs, FlowNode

W, H = 640, 360
PAD_L, PAD_R, PAD_T, PAD_B = 56, 16, 20, 44


def _fmt(v: float, unit: str) -> str:
    s = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    # Currency symbols read before the number; every other unit reads after.
    return f"{unit}{s}" if unit in ("₹", "$", "€", "£") else f"{s}{unit}"


def _nice_max(values: List[float]) -> float:
    m = max(values) if values else 1
    if m <= 0:
        return 1
    exp = math.floor(math.log10(m))
    base = 10 ** exp
    for step in (1, 2, 2.5, 5, 10):
        if m <= step * base:
            return step * base
    return 10 * base


def _hidden_table(a: ChartAttrs) -> str:
    head = "".join(f"<th scope=\"col\">{esc(s.name)}</th>" for s in a.series)
    rows = []
    for i, label in enumerate(a.labels):
        cells = "".join(f"<td>{esc(_fmt(s.values[i], a.unit))}</td>" for s in a.series)
        rows.append(f"<tr><th scope=\"row\">{esc(label)}</th>{cells}</tr>")
    return (f'<table class="vh"><caption>{esc(a.title)}</caption>'
            f'<thead><tr><th scope="col"></th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _legend(a: ChartAttrs) -> str:
    if len(a.series) < 2:
        return ""
    items = "".join(
        f'<li><span class="sw s{i}" aria-hidden="true"></span>{esc(s.name)}</li>'
        for i, s in enumerate(a.series))
    return f'<ul class="b-chart-legend">{items}</ul>'


def _gridlines(vmax: float, unit: str) -> str:
    out = []
    plot_h = H - PAD_T - PAD_B
    for k in range(5):
        y = PAD_T + plot_h * (1 - k / 4)
        val = vmax * k / 4
        out.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="b-tick" x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end">{esc(_fmt(val, unit))}</text>')
    return "".join(out)


def bar_chart(a: ChartAttrs) -> str:
    vmax = _nice_max([v for s in a.series for v in s.values])
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    n = len(a.labels)
    group_w = plot_w / n
    bar_w = min(48, (group_w * 0.7) / len(a.series))
    parts = [_gridlines(vmax, a.unit)]
    for i, label in enumerate(a.labels):
        gx = PAD_L + i * group_w
        total = bar_w * len(a.series)
        start = gx + (group_w - total) / 2
        for si, s in enumerate(a.series):
            v = s.values[i]
            h = plot_h * (v / vmax) if vmax else 0
            x = start + si * bar_w
            y = PAD_T + plot_h - h
            parts.append(
                f'<rect class="b-bar s{si}" x="{x:.1f}" y="{y:.1f}" width="{bar_w - 3:.1f}" height="{h:.1f}" rx="2">'
                f'<title>{esc(s.name)}: {esc(label)} {esc(_fmt(v, a.unit))}</title></rect>')
            if len(a.series) == 1:
                parts.append(f'<text class="val" x="{x + (bar_w - 3) / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle">{esc(_fmt(v, a.unit))}</text>')
        parts.append(f'<text class="b-lbl" x="{gx + group_w / 2:.1f}" y="{H - PAD_B + 20}" text-anchor="middle">{esc(label)}</text>')
    return _svg(a, "".join(parts))


def line_chart(a: ChartAttrs) -> str:
    vmax = _nice_max([v for s in a.series for v in s.values])
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    n = len(a.labels)
    step = plot_w / max(n - 1, 1)
    parts = [_gridlines(vmax, a.unit)]
    for i, label in enumerate(a.labels):
        parts.append(f'<text class="b-lbl" x="{PAD_L + i * step:.1f}" y="{H - PAD_B + 20}" text-anchor="middle">{esc(label)}</text>')
    for si, s in enumerate(a.series):
        pts = []
        for i, v in enumerate(s.values):
            x = PAD_L + i * step
            y = PAD_T + plot_h * (1 - (v / vmax if vmax else 0))
            pts.append((x, y))
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        parts.append(f'<path class="line s{si}" d="{d}" pathLength="1"><title>{esc(s.name)}</title></path>')
        for (x, y), v in zip(pts, s.values):
            parts.append(f'<circle class="b-dot s{si}" cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{esc(s.name)}: {esc(_fmt(v, a.unit))}</title></circle>')
    return _svg(a, "".join(parts))


def donut_chart(a: ChartAttrs) -> str:
    s = a.series[0]
    total = sum(s.values) or 1
    cx, cy, r = 120, 120, 84
    parts = []
    offset = 0.0
    for i, (label, v) in enumerate(zip(a.labels, s.values)):
        frac = v / total
        parts.append(
            f'<circle class="arc s{i % 4}" cx="{cx}" cy="{cy}" r="{r}" pathLength="100" '
            f'stroke-dasharray="{frac * 100:.2f} {100 - frac * 100:.2f}" stroke-dashoffset="{-offset:.2f}">'
            f'<title>{esc(label)}: {esc(_fmt(v, a.unit))} ({frac * 100:.0f}%)</title></circle>')
        offset += frac * 100
    legend = "".join(
        f'<text class="b-lbl" x="260" y="{60 + i * 28}"><tspan class="sw s{i % 4}">■</tspan> {esc(label)} · {esc(_fmt(v, a.unit))} ({v / total * 100:.0f}%)</text>'
        for i, (label, v) in enumerate(zip(a.labels, s.values)))
    body = f'<g class="donut">{"".join(parts)}</g>{legend}'
    return _svg(a, body, viewbox="0 0 640 240")


def _svg(a: ChartAttrs, body: str, viewbox: str = f"0 0 {W} {H}") -> str:
    desc = f"{a.kind} chart of {', '.join(s.name for s in a.series)} across {len(a.labels)} categories"
    if a.unit:
        desc += f", unit {a.unit}"
    return (f'<svg class="b-chart-svg k-{a.kind}" viewBox="{viewbox}" role="img" '
            f'aria-labelledby="{{TID}}" preserveAspectRatio="xMidYMid meet">'
            f'<title id="{{TID}}">{esc(a.title)}</title><desc>{esc(desc)}</desc>{body}</svg>')


def chart(a: ChartAttrs, block_id: str) -> str:
    fn = {"bar": bar_chart, "line": line_chart, "donut": donut_chart}[a.kind]
    svg = fn(a).replace("{TID}", f"{block_id}-t")
    return svg + _legend(a) + _hidden_table(a)


# ---------------------------------------------------------------------------
# Process flow
# ---------------------------------------------------------------------------
NODE_W, NODE_H, GAP = 150, 64, 46


def process_flow(nodes: List[FlowNode], block_id: str, title: str | None) -> str:
    n = len(nodes)
    width = n * NODE_W + (n - 1) * GAP + 24
    height = NODE_H + 40
    parts = []
    mid_y = 20 + NODE_H / 2
    # One path along the whole row for the pulse to travel.
    path_d = f"M12,{mid_y} H{width - 12}"
    parts.append(f'<path id="{block_id}-p" class="rail" d="{path_d}" pathLength="1"/>')
    for i, node in enumerate(nodes):
        x = 12 + i * (NODE_W + GAP)
        parts.append(
            f'<g class="node k-{node.kind}" transform="translate({x},20)">'
            f'<rect width="{NODE_W}" height="{NODE_H}" rx="10"/>'
            f'<text class="nl" x="{NODE_W / 2}" y="{NODE_H / 2 - (6 if node.sub else -5)}" text-anchor="middle">{esc(node.label)}</text>'
            + (f'<text class="ns" x="{NODE_W / 2}" y="{NODE_H / 2 + 14}" text-anchor="middle">{esc(node.sub)}</text>' if node.sub else "")
            + "</g>")
        if i < n - 1:
            ax = x + NODE_W
            parts.append(f'<path class="arrow" d="M{ax + 6},{mid_y} h{GAP - 18} m-8,-6 l8,6 l-8,6"/>')
    # The pulse follows the rail via CSS motion path (offset-path), so
    # prefers-reduced-motion can stop it. Its path is duplicated as a CSS
    # custom property because offset-path cannot reference an SVG id.
    parts.append(f'<circle class="pulse" r="5" style="offset-path:path(\'{path_d}\')"/>')
    hidden = "".join(
        f"<li>{esc(nd.label)}{(' — ' + esc(nd.sub)) if nd.sub else ''}</li>" for nd in nodes)
    return (f'<svg class="b-flow-svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{block_id}-t" '
            f'preserveAspectRatio="xMinYMid meet" style="aspect-ratio:{width}/{height}">'
            f'<title id="{block_id}-t">{esc(title or "Process flow")}</title>'
            f'<desc>{n} steps from {esc(nodes[0].label)} to {esc(nodes[-1].label)}</desc>'
            f'{"".join(parts)}</svg><ol class="vh">{hidden}</ol>')
