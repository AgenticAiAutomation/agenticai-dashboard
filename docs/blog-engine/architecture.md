# Blog Visual Engine — architecture

Status: Phase 1 (schema, validators, renderer, tokens, public CSS) and
Phase 2 (editor, storage, revisions, publish, migration) shipped 2026-09-18
behind `BLOG_ENGINE_V2`, default off. Nothing on the live blog changes until
the flag is flipped, and flipping it back restores today's behaviour exactly.

## Why blocks

The article editor used to produce a markdown string that became an HTML
string. Neither can be validated, scored per element, or re-rendered when the
design changes. A block array can:

- every block has a type and typed attributes, so a table without a caption
  or an image whose alt text is its filename is rejected at save time, not
  discovered on the page;
- structured data (`FAQPage`, `HowTo`, `VideoObject`, `ImageObject`) is
  derived from the blocks, so the markup and the visible page cannot disagree
  — marking up a question that is not on the page is a cloaking penalty;
- no user-written HTML reaches the page. Every string is escaped on render.
  The one exception, `legacy_html`, exists for migration and goes through an
  allowlist sanitiser (`sanitize.py`, backed by `nh3`);
- the same blocks can later render to RSS, AMP, email or an LLM feed without
  touching the editor.

## Data flow

```
dashboard editor  ──save──▶  article.content_blocks (JSONB)
                                       │
                                  parse_blocks()          schema.py
                                       │
                                  validate_article()      validate.py   ─▶ warnings / blocks
                                       │
                 ──publish──▶     render_page()           render.py + graphics.py + seo.py
                                       │
                          published/articles/<slug>/index.html      (the page, static)
                          published/articles/<slug>.json            (index/sitemap record, as today)
                          published/media/engine/blog-engine.<hash>.css   (block styles, cached)
                                       │
marketing site (Flask)   /blog/<slug>  ──▶  BLOG_ENGINE_V2 on and index.html exists?
                                              yes: send_file — zero template work
                                              no:  legacy path, byte-identical to today
```

Rendering happens once, at publish. A visitor costs the site one
`send_file`. `blog.py` still reads the JSON files for the index, the sitemap
and related-article lists, so those keep working for a mixed set of legacy
and v2 articles.

## The handoff contract

Two apps, one directory, one direction. The dashboard writes; the site reads.

| file | written by | read by | purpose |
|---|---|---|---|
| `articles/<slug>.json` | dashboard publisher | site `blog.py` | index, sitemap, related, metadata (unchanged) |
| `articles/<slug>/index.html` | dashboard `render_page()` | site `blog_post()` when flag on | the article page |
| `media/engine/blog-engine.<hash>.css` | dashboard publisher | browser via nginx `/static/blog/` | below-the-fold block styles, immutable cache |
| `media/**` | dashboard media pipeline | browser via nginx `/static/blog/` | images, posters, clips |

The JSON gains `content_format: "blocks"` on v2 articles. The site does not
need it; it is there so `scripts/rerender_all.py` can find them. Its `html`
field is the rendered article body, so a block article still renders through
the legacy template if the site's flag is off or `index.html` is missing —
that is fallback ladder step 1.

## Storage and the editor (Phase 2)

`seo_articles.content_blocks` (JSONB) is the source for a block article;
`content_format` is `'legacy'` for every existing row and `'blocks'` once an
article is saved from the block editor. The markdown columns are never
dropped; on every block save the API writes a **markdown projection**
(`convert.blocks_to_markdown`) into `team_edit_md` and syncs the FAQ table
from the `faq` block, so the existing 27-parameter scorer, Rank Math checks,
`/score`, and the legacy `html` fallback all keep working with no knowledge
of blocks. Phase 4 adds block-aware parameters on top; nothing is replaced.

`seo_article_revisions` keeps the last 50 saves per article with the meta
fields at that moment; restore writes a new revision rather than rewinding.

Endpoints (all 404 with the flag off; roles are the existing JWT roles):

| route | role | does |
|---|---|---|
| `GET /api/seo/blog-engine/status` | any | whether the engine is on (drives the Blocks link) |
| `GET /articles/{id}/blocks` | any | blocks, meta, report, `can_edit` / `can_publish` |
| `PUT /articles/{id}/blocks` | seo_lead+ | validate (422 names the block), store, project markdown, sync FAQs, revision, report |
| `POST /articles/{id}/blocks/preview` | any | the exact page for the editor iframe: no CSP meta, no analytics, both stylesheets inlined |
| `GET …/blocks/revisions`, `POST …/revisions/{n}/restore` | any / seo_lead+ | history |
| `POST /articles/{id}/blocks/publish` | admin | score ≥ 80 (not overridable), legacy blockers, block validators (admin override with an audited reason), then `index.html` + JSON + deferred CSS + IndexNow |
| `POST /api/seo/media/upload` | seo_lead+ | image for a block: MIME sniffed by decoding, EXIF stripped, ≤10 MB, no SVG, max 2400 px wide |

The editor (`web/app/dashboard/seo/articles/edit-v2/`) is three columns:
blocks, live preview, sidebar. Inline text is a contenteditable serialised to
runs-with-marks on every input (`components/blocks/RichText.tsx`); HTML never
leaves the component. Paste walks the pasted DOM the same way, so a Docs
`<span style="font-weight:700">` becomes a bold mark and a `<ul>` becomes a
list block. Autosave five seconds after the last change; Ctrl+S saves now.
Viewers get the same page read-only; seo_lead sees no Publish button.

## Page chrome

The article page carries the site's header, nav and footer so it is
indistinguishable from a legacy page. That markup is a verbatim copy of
`templates/blog-post.html` from the site repository, taken on 2026-09-18
(`templates/_chrome_header.html`, `_chrome_footer.html`, `_analytics.html`).

This is the one deliberate duplication in the design, and the trade is
stated here so nobody rediscovers it: the work order requires "Flask serves
a file" with zero per-request rendering, which rules out wrapping a body
fragment in the site's Jinja layout at request time. The cost is that a
change to the site's nav or footer does not reach v2 articles until they are
re-rendered.

Mitigation:

- every page carries `<meta name="generator" content="blog-engine <ver>; chrome <date>">`,
  so stale pages are greppable;
- `scripts/rerender_all.py` (Phase 2) re-renders every v2 article in seconds;
- the runbook lists "site chrome changed → re-render" as a step.

If this becomes a recurring cost, the Phase 6 option is to move the chrome
into two Jinja-free partials in the site repo that both the legacy template
and the renderer read. Not done now because it touches the legacy template,
which must stay byte-identical through this build.

## Stylesheet

`design_tokens.json` is the single source. `css.py` compiles it into:

- **critical** (≈7 KB, inlined in `<head>`): tokens as custom properties,
  layout, typography, marks, headings, figures, key takeaways, TOC, reading
  bar, reveal hooks, reduced-motion;
- **deferred** (≈12 KB, linked, content-hashed): every other block's styles.

Every selector is scoped under `.page-blog-v2`, checked by test, so the
sheet cannot affect a legacy page even if it were loaded there. Inner class
names carry a `b-` prefix because the site's `components.css` already owns
`.stat`, `.tag`, `.bar` and others.

The site's own `tokens.css`, `base.css` and `components.css` are still linked
— they style the chrome. The article body uses only the engine's sheet.

## Motion

CSS-first, and every animation is on `transform` or `opacity`:

| effect | mechanism | JS |
|---|---|---|
| reading progress bar | scroll-driven animation (`animation-timeline: scroll()`), hidden where unsupported | 0 |
| process-flow pulse | CSS motion path (`offset-path` / `offset-distance`) | 0 |
| chart draw-in | `stroke-dasharray` on paths with `pathLength="1"` | 0 |
| scroll reveal | `data-reveal` hook; Phase 5 script adds `html.js` and `.in` | ≤2 KB (Phase 5) |
| stat count-up, YouTube swap-in, copy button, slider drag | Phase 5 | ≤1–2 KB each |

SMIL `<animate>` is not used anywhere: it cannot be switched off by
`prefers-reduced-motion`, and the rule is that reduced motion means no motion.

Without JavaScript the page is complete: reveal blocks are visible (the
hiding rule is gated on `html.js`), the YouTube facade is a real link, the
compare slider is two labelled images, the code block simply has no copy
button.

## Security

- Blocks are structured JSON; every string is HTML-escaped on render.
- `legacy_html` is the only markup passthrough, sanitised by `nh3` against a
  narrow allowlist (no `style`, `class` (except `language-*` on `code`),
  event handlers, `iframe`, `svg`, `data:` image URLs).
- Link `href`s are validated at parse time (`http(s)`, site-relative,
  `#anchor`, `mailto:` only); external links get `rel="noopener"`.
- The page carries a CSP `<meta>`: `script-src 'self'` plus the GA and Google
  Preferred Sources hosts and a SHA-256 of the one inline GA snippet;
  `img-src` adds `gstatic.com` because the Preferred Sources button loads its
  logo from there. This deviates from the work order's literal policy, which
  would have blocked analytics the site already runs on every page.
- The site's `/blog/<slug>` route rejects slugs containing `/` or `..` before
  touching the filesystem.

## Testing

- `api/tests/blog_engine.py` — 86 offline checks: schema rejections, token
  contrast (WCAG ratios computed), CSS budget and scoping, renderer
  invariants, determinism, sanitiser, JSON-LD, validators.
- `AgenticWeb/tests/blog_engine_flag.py` — 12 checks on the site: flag off is
  today's site, flag on serves the file, legacy article byte-identical either
  way, ETag/304, traversal blocked.
- Phase 1 exit was demonstrated by serving the fixture through the real Flask
  app locally: 0 console errors, no horizontal scroll at 360 px, full content
  with JavaScript disabled, no animation under reduced motion, keyboard
  reaches TOC / FAQ / table / CTA.

## Module map

```
api/app/blog_engine/
  design_tokens.json   single source for colour, type, space, effects, rhythm
  schema.py            block models (pydantic, discriminated on type), parse_blocks()
  inline.py            runs + marks -> escaped HTML; slugify; word count
  graphics.py          bar / line / donut charts and process flow as SVG
  render.py            per-block renderers, render_article(), render_page()
  seo.py               JSON-LD from RenderResult
  css.py               tokens -> critical + deferred stylesheet, scoped
  validate.py          effect limits, rhythm, structure, meta, links
  sanitize.py          nh3 allowlist for legacy_html
  templates/           page.html + chrome partials copied from the site
  fixtures/            sample-article.json (all 21 block types)
api/scripts/render_fixture.py        render the fixture to a directory
api/scripts/gen_block_schema_doc.py  regenerate docs/blog-engine/block-schema.md
```
