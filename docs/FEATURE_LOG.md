# Feature log

One line per change that reaches production. Appended automatically by
`ops/stamp-feature-log.sh` (called from `ops/deploy.sh`), and by hand for
anything notable. This is the human-readable companion to `bo_audit`; it answers
"what did we add, and when" without reading git.

## Convention

```
- <UTC timestamp> · <feature> · <action> · <ref> · by <who>
```
Add a free-text line under a release heading when the change affects what the
team sees — especially a scoring or level change, which they must be told about
before it lands.

---

## 2026-11-10 · Blog Playbook v2 (flagged) — built, not deployed

Behind the new sub-flag `BLOG_PLAYBOOK_V2` (default `false`), on top of the
existing Playbook access. Branch `feat/blog-playbook-v2` here (from
`feat/blog-playbook`) and in AgenticWeb (from `main`). Spec:
`BLOG_PLAYBOOK_V2_CHANGES.md`. Guide: `docs/BLOG_PLAYBOOK.md` § v2.

**Root cause — bold and links "not accepted":**
1. *H2 sections:* the builder kept `**…**` and `[..](..)` in `body_md` fine,
   and inline bold already reached the site as `<strong>`. But both Markdown
   normalisers (`playbook_render.normalise` and the legacy
   `_normalise_markdown`) promote any line that is **entirely** bold to an
   `### H3`. A bold lead sentence on its own line — the usual way writers use
   bold — therefore came out as a heading, never as bold. The builder also
   offered no bold control and only mentioned links.
2. *FAQ answers:* answers are not part of `body_md`. The publisher sends them
   to the site as plain text and `blog-post.html` prints `{{ f.answer }}`
   autoescaped, so `**` and `[..](..)` showed literally. (`_faq_html()` in
   `routes/articles.py` was not on this path at all — nothing calls it.)

Fix: the v2 renderer (`to_html(md, v2=True)`) does not promote bold lines;
FAQ answers are converted (bold + links only, everything else escaped) to
`answer_html` for the page, and `answer` becomes plain text for the FAQPage
JSON-LD. v1 output is byte-identical (snapshot test).

Changes:
- Writer: B (Ctrl+B) / Link toolbar on H2 paragraphs, table text-below, real
  example description, callout and FAQ answers. Not on the TL;DR. Links must
  be `https://…` or `/…`; `javascript:` etc. are refused in the builder and
  stripped by the renderer. External links get `target="_blank" rel="noopener"`.
- Sections hold many ordered items: paragraph, steps, flow, table (any number,
  each with caption + text below), image, real example, cost table (editable
  columns), callout. Reorder up/down, remove.
- Images: upload only, WebP exactly 1536 × 1024, checked on the server (magic
  bytes + Pillow). `POST /api/seo/articles/{id}/upload-inline-image`,
  `DELETE /api/seo/articles/{id}/inline-image?url=` (kept while live).
  Rendered as `<figure>` with fixed width/height. Featured image unchanged.
- Callout: exactly one per article, free-text label ≤ 30 chars, reserved
  labels refused. Playbook blocker: 0 → "Add one callout before submitting.",
  > 1 → "Only one callout per article." Also blocks: real example with no
  numbers, inline image with no alt, a disallowed link. No score points move.
- From the author: optional Best pick, Notice from author, Must do (1–5).
  Nullable columns, migration `004_playbook_author_extras`. Not counted in the
  120 words.
- Skim (advisory): no real example / no table → check skipped (0 of 0), total
  = earned ÷ available; `parameters_skipped` returned.
- v1 articles open in v2 with no body change: the old fixed example / cost
  blocks become their own trailing sections (`toV2`), nothing is written until
  the writer saves.
- Website: callout class for any non-reserved label, figures, author boxes,
  FAQ `answer_html`, homepage "Latest from the blog" (3 posts, 10-min cache,
  hidden on error).
- **Unchanged:** `scoring.py`, `rankmath.py`, 80 rule, every existing publish
  blocker. Old articles score and render as before.

Flag / rollback: `bash /root/blog-playbook-flag.sh v2-off` (L1) → redeploy
previous commits (L2) → `alembic downgrade 003_playbook_blocks` (L3, drops only
the three new nullable columns). See `docs/BCP_AND_ROLLBACK.md`.

- 2026-11-10T00:00:00Z · blog-playbook-v2 · build (flag off, not deployed) · feat/blog-playbook-v2 · by claude-code

## 2026-10-13 · Per-site levels, Daily Tracker, Idea Board, /articles removed — built, not deployed

- Team-visible once the flags go on: each associate's Backlink Ops score becomes **their own
  links at their own level per website** (was: the whole site's sheet). Tell the team first.
- Tracker marks: base × quality (1–5 → 0–1.5×), late = 50%, Backlink Ops links 5 each up to 20/day.
- See `docs/DAILY_TRACKER.md` and the team guide `docs/DAILY_TRACKER_GUIDE.md`.

## 2026-10-08 · Article HTML export (above the threshold)

- Writer page → Scores: **Export HTML** appears once the house score reaches 80.
  It only works while the screen still matches what was scored; any edit asks
  for Save & score again.
- One self-contained, always-light `.html` file: title, featured image
  (embedded), body (same converter as publish, Playbook boxes styled), From the
  author, FAQs. `GET /api/seo/articles/{id}/export.html`; 409 below 80.
- No scoring, gate or publisher change. `api/app/seo/services/export_html.py`, tests
  `tests/test_export_html.py`.

## 2026-10-05 · Blog Playbook writer (flagged) — built, not deployed

Answer-first block writer on the article page, behind `BLOG_PLAYBOOK_ENABLED`
(default off) and `BLOG_PLAYBOOK_USERS`. Branch `feat/blog-playbook` in this
repo and in AgenticWeb. Full guide: `docs/BLOG_PLAYBOOK.md`.

- Writer page: **Playbook | Raw Markdown** switch. The builder composes the same
  `body_md`, and the raw editor is always there.
- Advisory **Skim score** dial: `GET /api/seo/articles/{id}/skim`. It never blocks publish.
- New nullable column `seo_articles.playbook_blocks` (migration
  `003_playbook_blocks`). It is not mapped on the model, so it is unused while the flag is off.
- AI draft: `DRAFT_SYSTEM_PLAYBOOK` beside the unchanged `DRAFT_SYSTEM`, used
  only with the flag on.
- Publish: Playbook posts (flag on + TL;DR) use a converter that keeps tables
  and separate blockquotes. All other posts use the old converter, unchanged.
- **No scoring change.** `scoring.py`, `rankmath.py`, `golive.py`,
  `publisher.py` are untouched; the publish gate is still 80.
- Nav: "Playbook guide" → Scoring guide § Blog Playbook.
- 2026-10-05T07:30:00Z · blog-playbook · build (flag off, not deployed) · feat/blog-playbook · by claude-code

## 2026-10-01 · invoice-desk v1.1.0 — business type, price list, loud stamp

- Client form + desk + PDF: **Nature of business** field.
- **Price list** (Settings): item, SAC, price. Picking an item on an invoice
  fills SAC + price; client submissions are pre-priced from it. 0 = set per invoice.
- PDF: boxed red **THIS IS A SYSTEM GENERATED INVOICE** under the total, plus a
  red line in the footer of every page. Layout tightened to stay on one page.
- No schema change (price list lives in `inv_settings`). Tests 46 → 52.

## 2026-10-01 · invoice-desk v1.0.0 — client fill links, review queue, PDF

New, separate module `api/app/invoice_desk/` (own SQLite, own prefix, flag
`INVOICE_DESK_ENABLED`). Nothing existing changed except two lines in
`api/app/main.py` and one dependency (`reportlab`). Full guide:
`docs/INVOICE_DESK.md`.

- `/invoices/` desk (Jai only): Review queue, Issued, Fill links, Settings.
- `/invoices/f/<token>` public form: client details + services; no prices by default.
- Approve & issue → next number (starts **AI-102**), locked, PDF in the AI-101
  layout; GST split CGST+SGST / IGST by place of supply; round-off; amount in words.
- Void + Duplicate for corrections. Backup before every issue. Audit trail.
- Tests: `tests/test_invoice_desk.py` (46 checks).

## 2026-10-01 · backlink-ops v1.2.0 — LettStartDesign + all-projects tracking

- **LettStartDesign.com** added as a live project (`lettstart`, purple) with
  20 seed keywords. Page paths ship as `/` — fill the real ones on the desk.
- **All projects tab** (`GET /api/seo/backlink-ops/progress`): today per
  website (links, approved, pending, sent back, points, queries, who), a
  14-day heat grid per website, and 14-day totals per person across every
  site. Fixes the gap where the Scoreboard only showed each associate's
  rostered project — work on any other site was invisible.
- Read-only addition. No schema change (v1), no scoring change, existing
  tabs untouched. Smoke test grows 51 → 61 checks.

## 2026-09-15 · backlink-ops v1.1.0 — the desk reviews itself

Prompted by the first week live: every link waited for Jai (the opposite of
the point), and the Level 1 target of 60 points was 4-10 links for a team that
does 30-40 a day each.

- **Automatic review** (`autoreview.py`, `POST /api/seo/backlink-ops/auto-review`,
  `ops/auto-review.sh`). Hourly, 9 AM–8 PM IST: opens each pending link,
  confirms our domain + anchor + real dofollow/nofollow on the page, applies
  the hard rules (404, link absent, spam > 5%, third link on one site), and
  sends the rest to the AI in one batched call. Approves and sends back on its
  own; only the ambiguous reach the Review queue, marked *Needs a human look*.
  Reviewer is recorded as `auto` or `ai`; every decision is in the audit trail
  with its reason. Rules-only when the AI is off. `BACKLINK_OPS_AUTOREVIEW=0`
  turns it off without a deploy.
- **Ladder recalibrated, and a links floor.** Level 1 is now 250 points *and*
  40 links a day (L2 300/45, L3 350/50, L4 420/55, L5 500/60). Tests updated
  deliberately (`test_scoring.py`). The associates' checklist gains a line.
- **Level targets editable on the desk** — points, links, queries, average DA
  and high-value per level, bounded, stored in `bo_config['levels']`.
- **Websites editable on the desk** — add a site (id, domain, name, pages,
  niche, seed keywords, Live tick) without a deploy; `bo_config['projects']`
  merges over the seed. Every project now carries a `domain` (the verifier
  needs it). **WhatsAppAutomation.co.in** ships in the list, not live.
- Inactive sites are hidden from associates' project switch; the superuser
  sees them greyed.
- Health reports version 1.1.0. Schema unchanged (v1): the run summary and
  overrides reuse `bo_config`.

## 2026-09 · backlink-ops v1.0.0 — initial install

Target: `agenticai-dashboard` (FastAPI). The Flask marketing site at
`/var/www/agenticai` is not involved. The existing `seo_backlinks` table,
`/api/seo/backlinks*` routes and article pipeline are untouched — the desk is a
separate feature with its own database at a separate prefix.

Added, as a self-contained module under `api/app/backlink_ops/`:

- **Off-page desk** at `/seo/backlink-ops` — daily link logging with live
  server-side scoring, and a requirement checklist per difficulty level.
- **Scoring engine** (`scoring.py`) — base points by link type, DA multiplier,
  dofollow / relevance / indexed bonuses, spam and repeat-domain penalties,
  exact-match anchor ratio. Deterministic and unit-tested; points are recomputed
  from source rows, never stored.
- **Difficulty ladder**, 5 levels, starting at Level 1 (60 points, 3 keyword
  queries, average DA 20+). Superuser-settable.
- **Keyword Lab** — one Ubersuggest query at a time, seeded with 25 keywords per
  site (AgenticAI: hospitals, insurance, banking, back office, CA/CS firms,
  appointment systems, WhatsApp automation · DIYMart: Mr. DIY head-to-head,
  gifting, DIY ideas). Paste-in, verdict out, keyword bank accumulates.
- **AI layer** (`ai.py`) — keyword verdicts and a daily coach review, via Grok
  (default), Gemini or Anthropic, with deterministic rule-based fallbacks and a
  daily call cap. Advisory only; it never computes a score.
- **AI self-test** — `POST /api/seo/backlink-ops/ai-selftest` (superuser) makes
  one live call and reports whether the provider returns parseable JSON. Needed
  because a broken provider is otherwise invisible: verdicts silently fall back
  to rules rather than erroring.
- **Review queue** — superuser approves / sends back / rejects; rejected links
  stop counting and return to the associate with a note.
- **Scoreboard** — 14-day points per associate against the level target, streak,
  targets hit, keywords analysed.
- **Roles** — mapped from the dashboard's own, with no change to its users
  table: Jai (by email) is superuser; `admin` and `seo_lead` are desk admins;
  `viewer` is read-only. Enforced server-side in `service.py`, on every call.
- **Framework-adaptive structure** — all logic in a framework-free
  `service.py`; thin `adapters/fastapi_app.py` and `adapters/flask_app.py`.
  `register(app)` detects which it was given. The page needs no template
  engine.
- **Audit trail** (`bo_audit`) plus `[backlink-ops]`-prefixed stamping into the
  existing application log. No new log file, no logging config changed.
- **Ops** — `preflight.sh`, `deploy.sh` (health-gated with automatic rollback),
  `rollback.sh` (3 levels), `healthcheck.sh`, nightly backup.

Not changed: no existing route, template, model, migration, dependency or
logging handler. Registration is a single defensive call that returns `False`
rather than raising if anything is wrong, and the feature is off unless
`BACKLINK_OPS_ENABLED=1`.

Added at go-live (2026-09-15), after the first deploy showed the page treating
every visitor as anonymous:

- **Token mode for the page** — `BACKLINK_OPS_TOKEN_STORAGE_KEY` /
  `BACKLINK_OPS_LOGIN_URL`. This dashboard keeps its JWT in
  `localStorage['access_token']` and sends it as a header, never a cookie, so
  the page now attaches the same header, and a 401 goes to `/login/` instead of
  reloading in a loop. Opt-in; blank = as shipped. Served same-origin with the
  frontend via nginx (`sites-available/dashboard-frontend`). See RUNBOOK.
- 2026-09-14T11:57:33Z · backlink-ops · install · d1e472e · by unknown
