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

## [BLOG_ENGINE_V2 — Phase 0] 2026-09-18
Added:      docs/state/2026-09-18-preflight.txt; /var/backups/blogengine/
            (site + dashboard tarballs, DB dump, SHA256SUMS; restore rehearsed)
Changed:    marketing site now on tracked main 315e830 — blog.py and 17
            uncommitted edits committed to rescue/prod-state-20260918,
            main fast-forwarded to it; no file on disk changed, no restart
Migration:  none
Flag state: BLOG_ENGINE_V2 not yet introduced (default false when it is)
Rollback:   git checkout server-state-20260824-pre-expand is the same tree;
            full restore: tarballs in /var/backups/blogengine/
Verified by: fingerprint of every file before/after identical; /blog 200;
            origin/main == production HEAD
