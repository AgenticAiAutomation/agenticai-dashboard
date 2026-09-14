# Backlink Ops — architecture

## What it is

A daily off-page SEO desk for two associates working two sites
(agenticaiautomation.co and DIYMart.in), bolted onto `agenticai-dashboard` as a
**self-contained feature module**. It scores submitted backlinks, walks the
associate through Ubersuggest one keyword at a time, grades the day, and gives
Jai an approval queue.

It sits *beside* the dashboard's existing SEO and article features, not on top
of them. The `seo_backlinks` table and the `/api/seo/backlinks*` routes are
live and are never read, written or shadowed by this module. Two trackers is a
deliberate, temporary state: the old one keeps working while the desk proves
itself, and merging them — if ever — is a separate decision with its own
migration.

## The one design rule

> The host dashboard must keep working exactly as it does today, whatever
> happens to this module.

Everything below follows from that rule.

| Decision | Why |
|---|---|
| Its own SQLite file, not new tables in the dashboard DB | A bug here cannot lock, migrate or corrupt existing data — `seo_backlinks` and the article pipeline are in a database this module never opens. Backup and restore are independent. Uninstall is `rm` of one file. |
| Registered by one defensive call, wrapped in `try/except` | If the module fails to import or its DB is unreachable, the app logs it and boots anyway. A feature must not be able to take the site down. |
| Off unless `BACKLINK_OPS_ENABLED=1` | The rollback of first resort is a flag flip, not a git revert. |
| Routes namespaced under `/seo/backlink-ops` and `/api/seo/backlink-ops` | Distinct from the existing `/api/seo/backlinks`. `register()` flattens nested routers and `Mount`s, then refuses to mount if anything already serves those prefixes — and compares whole path segments, so `/api/seo/backlinks` is correctly *not* read as a clash. |
| No new Python dependencies | `pip install` is the step most likely to break an unrelated part of the app. The AI layer uses `urllib`; the page needs no template engine, just two string replacements. |
| Business logic in `service.py`, framework only in `adapters/` | The dashboard is FastAPI and the marketing site is Flask. One service layer with two thin adapters means the two can never drift, and the tests prove both give the same answers. |
| Identity read from the host's existing auth, never created here | No second login, no second password store, no session conflict. |
| Scoring is pure Python, no AI in the loop | The associates' target has to be reproducible and auditable. AI comments on the result; it never computes it. |

## Request path

```
browser
  └─ GET /seo/backlink-ops/          → adapters/fastapi_app → service.page_html()
  └─ GET /api/seo/backlink-ops/day   → adapters/fastapi_app → service.day(user, ...)
                                          │                      │
                        identity.py ──────┘                      ├─ store.py  (its own sqlite)
                    (host JWT → role)                            ├─ scoring.py (pure)
                                                                 └─ audit.py  (host logger + bo_audit)
```

The adapter's only jobs are finding the current user and turning
`(status, payload)` into a response. Swapping FastAPI for anything else is one
new file in `adapters/`.

## Modules

| File | Responsibility | Change it when |
|---|---|---|
| `config.py` | Every setting, all from the environment | Adding a new tunable |
| `identity.py` | Maps the host's user and role onto superuser / admin / viewer | Your role names change |
| `service.py` | **Every endpoint's logic and policy**, framework-free | Adding or changing a feature |
| `adapters/_userhook.py` | Finds the user the host authenticated (hook → state → JWT) | Your auth stack changes |
| `adapters/fastapi_app.py` | FastAPI routers (thin) | Adding an endpoint |
| `adapters/flask_app.py` | Flask blueprints (thin) | Adding an endpoint |
| `seed.py` | Link types, difficulty ladder, seed keyword clusters, projects | Adding a site or a keyword cluster |
| `scoring.py` | The scoring formula and the daily requirement checklist | **Never casually** — see tests and FEATURE_LOG |
| `store.py` | SQLite access, schema, backup, history | Adding a table or a query |
| `ai.py` | Keyword verdicts and the day coach, with rule-based fallbacks | Swapping AI provider |
| `audit.py` | Log stamping to the host logger + `bo_audit` | Never bypass it on a write |
| `templates/backlink_ops/index.html` | The whole UI, inlined. Plain HTML with two `__BO_*__` placeholders — no template engine | UI changes |

## Roles

| Role | Who | Can |
|---|---|---|
| `superuser` | Emails in `BACKLINK_OPS_SUPERUSERS` (Jai) | Everything, plus approve/reject links, change the difficulty level, edit the team, read the audit trail, trigger a backup |
| `admin` | Dashboard roles in `BACKLINK_OPS_ADMIN_ROLES` — `admin`, `seo_lead` | Log links, keyword lab, both sites, AI coach, scoreboard. **Cannot** approve, change the level, or touch roles |
| `viewer` | Dashboard role `viewer`, or authenticated with no recognised role | Reads everything, writes nothing |
| — | Not signed in | 401. There is no anonymous mode in production (`BACKLINK_OPS_ALLOW_ANON=0`) |

Nothing is written to the dashboard's users table. Superuser is decided by
email in the service environment, so escalation needs server access rather than
a UI click.

Enforcement is on the server, in decorators, on every route. The UI hides what a
role cannot do, but hiding is a courtesy — the 403 is the control.

## What is deliberately NOT here

- No scheduler, no background worker. Everything is request-driven.
- No email or WhatsApp notification. Add it later against the `bo_audit` stream.
- No Ubersuggest API integration. The associates paste; that is the workflow Jai
  asked for and it costs nothing.
