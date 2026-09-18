# Design tokens and named effects

Source of truth: `api/app/blog_engine/design_tokens.json`. The dashboard
preview and the public article page both compile from it (`css.py`). Change
the file, re-render, and every article follows. Writers never see a hex
value or a pixel size; they pick a token or a named effect.

## Where the values come from

The marketing site is single-theme by intent — a high-contrast signal board
on near-black. The engine does not introduce a second palette. Every colour
in the token file is the site's own, from `static/assets/css/tokens.css`,
mapped onto a role name:

| role | value | site name | use |
|---|---|---|---|
| `ink` | `#faf7f1` | `--paper` | body text, headings |
| `ink-muted` | `#a99d89` | `--paper-dim` | captions, labels, secondary text |
| `ink-faint` | `#6d6254` | `--paper-faint` | credits, sources |
| `surface` | `#0a0908` | `--void` | page |
| `surface-raised` | `#15120e` | `--carbon` | cards, callouts, tables |
| `surface-raised-2` | `#1d1913` | `--carbon-2` | table header rows |
| `brand` / `brand-hi` | `#ff5a00` / `#ff7d33` | `--orange` | links, step numbers, first chart series |
| `accent` | `#ffd400` | `--yellow` | highlights, TOC active, result callouts |
| `signal-positive` | `#2fd07f` | `--good` | tip callouts, checklist ticks |
| `signal-warning` | `#ffa23a` | `--warn` | warning callouts |
| `signal-negative` | `#ff4d3d` | `--bad` | reserved |
| `rule` / `rule-2` / `rule-3` | 10 / 18 / 28 % paper | `--hair*` | borders |
| `on-bright` | `#170800` | `--ink` | text on a bright background only |

`on-bright` is the site's `--ink`, which is near-black. It is for text sitting
on orange or yellow — never for text on the page. That mistake produced
invisible headings once; the name is meant to make it hard to repeat.

## Highlight tokens

A marker highlight is a bright background with dark text on it. Each pair is
contrast-tested in `tests/blog_engine.py`; the build fails below 4.5:1.

| token | background | text | ratio |
|---|---|---|---|
| `amber` | `#ffd400` | `#170800` | 13.7 |
| `mint` | `#7ff0b8` | `#0a0908` | 14.3 |
| `sky` | `#8ed0ff` | `#0a0908` | 12.0 |
| `rose` | `#ffb3c1` | `#170800` | 11.6 |

## Type

Two families above the fold, both already self-hosted by the site and
preloaded: **Archivo** (display, 700–900) for headings, stat numbers and step
numerals; **IBM Plex Sans** for body. **IBM Plex Mono** is for labels, table
headers and code only.

The scale is fluid — `clamp()` between a phone and a desktop size:

| token | value |
|---|---|
| body | 15 → 18 px |
| lead | 18 → 22 px |
| small | 13 → 15 px |
| h1 | 1.8 → 3.4 rem |
| h2 | 1.45 → 2.2 rem |
| h3 | 1.2 → 1.55 rem |
| h4 | 1.05 → 1.25 rem |
| stat | 2.4 → 4.6 rem |
| measure | 68 ch |

## Space, radius, shadow

4 px base, eight steps (`4 8 12 16 24 32 48 72`). Three radii (`4 8 14`),
three shadows. Blocks use the steps; nothing sets an ad-hoc margin.

## Layout

| token | value | meaning |
|---|---|---|
| `column` | 68 ch | the text column |
| `breakout` | min(1100 px, 100 vw − 32 px) | a visual escaping the column |
| `gutter` | 16 px | side padding on phones |
| `toc-min-width` | 1100 px | below this the TOC collapses above the article |

## Named effects and their limits

Writers get named effects, not a colour picker. Limits are enforced at save
time by `validate.py`: exceeding one is a warning in the editor and costs
score; a contrast failure is a hard block.

| effect | where | limit | how to apply |
|---|---|---|---|
| Lead paragraph | first paragraph of the article or a section | 1 per section | `paragraph.attrs.variant = "lead"` |
| Gradient headline | h2 only | 2 per article | `heading.attrs.gradient = true` |
| Marker highlight | inline | 4 per article | `highlight` mark with a token |
| Drop number | `steps`, `stat_band` | — | automatic |
| Breakout width | image, gallery, compare, video, table, chart, flow | any | `attrs.layout = "breakout"` |
| Sticky section label | h2 | automatic | the TOC tracks the current h2 on desktop (Phase 5 script) |

Why the limits: two gradient headlines make a page feel designed; six make
it feel like a slide deck. Four highlights draw the eye to four things; ten
draw it to nothing.

## The rhythm rule

The anti-wall-of-text rule, also in the token file so the editor and the
validator agree:

- no more than **250 words** between two visual blocks;
- at least **1 visual per 400 words** (image, gallery, compare, video, table,
  chart, flow, stat band, quote, callout, steps, code);
- a `key_takeaways` block in the first four blocks;
- at least one `faq` block.

## Motion tokens

`reveal_rise` 12 px, `reveal_ms` 480, one easing curve. All motion is on
`transform` and `opacity` and is removed entirely under
`prefers-reduced-motion: reduce`.
