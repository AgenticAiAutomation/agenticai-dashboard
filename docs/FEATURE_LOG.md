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

## 2026-09-25 · wa-funnel v1.0.0 + wa-leads v1.0.0 — a form in front of WhatsApp, and the desk behind it

Two pieces, one pipeline. `wa.agenticaiautomation.co` asks four short questions
before a visitor can message us — only the questions their earlier answers make
relevant — and `/dashboard/leads` is where the team works the result.

### The funnel (separate repo, separate service)

Flask + gunicorn + SQLite on **port 5006**, `wa-funnel.service`, its own nginx
block. Nothing on the marketing site (5001), the blog, Leadwa (5002),
agentic-platform (5003), the dashboard API (5004) or content-brain (5005) is
touched, and `ops/healthcheck.sh` fails the deploy if any neighbouring port
stops answering.

**On 5006, not 5005.** The spec said 5005 was free; it is not —
`content-brain.service` is bound to it, and taking it would have broken that
service. That near-miss produced `docs/VPS_SERVICES.md`, now the one registry
of what runs on this box; several older deploy docs here still name the
dashboard API as 5003 and now point at it. It also records two findings not
fixed: content-brain answers on `187.127.173.209:5005` from the public
internet (binds 0.0.0.0, no nginx block), and `ufw status` is inactive.

- **Branching flow** — intent decides which service chips appear; picking an
  industry reveals a subtype list and a pain-point checklist written for that
  industry. Eight sectors, taken from the reference build
  `wa-funnel-sample.html` along with all of the copy.
- **Relevancy score, server-side only, out of 100.** Qualify at 60, tunable
  through `QUALIFY_THRESHOLD` in the unit file — no redeploy. The score is
  never sent to the browser; a test asserts that. Above the line a visitor
  gets a prefilled `wa.me` deep link, below it a "within 2 business days"
  promise. **Every lead is stored and notifies the team either way** — the
  threshold only decides which screen they see.
- **Consent is required and timestamped.** No link and no notification without
  it; the refusal is in the route, not just the template.
- **Industries live in `config/industries.json`**, not in code — a sector is a
  text edit and a restart. Same for dial codes, languages and chips.
- **Abuse:** server-side validation against that config, 5 attempts per IP per
  hour counting failures, honeypot, 24h dedupe on number + email, salted IP
  hashes.
- **Fallback:** if gunicorn is down nginx serves a static page with a plain
  WhatsApp link instead of a 502. Rollback is four levels. Works with
  JavaScript off. 44 tests.

### The leads desk (this repo, `/dashboard/leads`)

A CRM over the funnel's leads, added as a self-contained module under
`api/app/wa_leads/` and **off unless `WA_LEADS_ENABLED=1`**. With the flag off
the endpoints do not exist and the dashboard is unchanged; with it on but the
funnel not yet deployed they answer 503 naming the missing file, so the page
explains itself instead of erroring. Registration mirrors backlink-ops: it
logs and returns False rather than raising, because a feature must not be able
to take the dashboard down — and this one depends on a file owned by a
different service.

- **Pipeline:** new → contacted → on hold → converted | rejected. Any move is
  allowed, because that is what happens; what is enforced is that every move
  is recorded in `lead_status_events` with the actor, the timestamp, the
  previous status and an optional note. The update and the history row go in
  one transaction.
- **One database, no sync.** The dashboard opens the funnel's SQLite directly
  (both run as `www-data`; the funnel sets WAL). Listing connections are
  read-only via a `file:…?mode=ro` URI — a test asserts a read path cannot
  write. The dashboard never creates, edits or deletes a lead.
- **Reading is open to any signed-in user; writing is not.**
  `WA_LEADS_WRITE_ROLES` gates it, `/meta` returns `can_write` so the page
  hides controls it would only be refused on, and every change is attributed.
- **Conversion rate counts decided leads only.** Counting open leads as
  "not yet converted" makes the rate fall whenever marketing works.
- The **fit score** is shown here — hidden from the visitor, and the whole
  point internally, so it sorts and filters. A lead with **no consent** is
  flagged red and gets no one-click `wa.me` link. The **`ip_hash` is stripped
  server-side** and never reaches the browser.
- Filter by status, industry, fit and age; search name, email or number; sort
  any column; paginated. `sort` is allowlisted before it reaches the ORDER BY
  — a test posts a `DROP TABLE` as the sort key.
- 44 store checks + 32 HTTP checks, neither needing Postgres or a token.
  `docs/WA_LEADS.md` has the rest.

Still open on the funnel side and not code: the notification channel is `none`
(no SMTP credential or webhook URL yet, so nothing pages the team), and the
"within 2 business days" line needs a person who owns that window.

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
