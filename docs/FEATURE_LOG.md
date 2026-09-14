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
