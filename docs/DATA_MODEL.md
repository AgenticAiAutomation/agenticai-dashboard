# Backlink Ops — data model

One SQLite file, default `instance/backlink_ops.db`, WAL mode. Every object is
prefixed `bo_`. The dashboard's own database — `seo_backlinks`, users, articles
— is never opened by this module.

`BACKLINK_OPS_DB` is resolved relative to the service's `WorkingDirectory`. If
that is not the repo root, set an absolute path.

## Tables

### `bo_entries` — one submitted backlink
| Column | Notes |
|---|---|
| `id` | `e` + 12 hex chars, generated server-side |
| `project` | `agenticai` \| `diymart` |
| `date` | `YYYY-MM-DD` in **IST** — the working day, not UTC |
| `author` | display name of the associate who logged it |
| `url`, `host` | `host` is normalised (lowercased, `www.` stripped) and drives the repeat-domain penalty |
| `type` | key from `seed.LINK_TYPES` |
| `da`, `spam` | numbers the associate read off their tool |
| `follow` | `dofollow` \| `nofollow` \| `unknown` |
| `target`, `anchor`, `kw` | our page, the anchor used, the keyword cluster it supports |
| `relevant`, `indexed` | 0/1 |

Points are **not stored**. They are recomputed from the row every time, so a
corrected formula corrects history instead of leaving two generations of numbers
in one table. Cost: a few hundred rows of arithmetic per request.

### `bo_reviews` — Jai's decision, one row per entry
`status` ∈ `approved` \| `rejected` \| `needs_fix` \| `pending`. A missing row
means pending. `rejected` removes the entry from the day's score; `needs_fix`
keeps the points but blocks day completion until cleared.

### `bo_queries` — one Ubersuggest query the associate ran
Keeps the raw paste (`raw`, capped at 8 KB) so a verdict can be re-derived later
without asking them to run it again. Counts toward the daily query requirement.

### `bo_bank` — the keyword bank, keyed `(project, kw)`
The analysed verdict per keyword: volume, difficulty, CPC, chase/park/drop, the
recommended target page, anchor rotations, and the off-page plan. Re-analysing a
keyword updates the row rather than duplicating it.

### `bo_coach` — the AI day review, keyed `(project, date, author)`

### `bo_config` — single row `settings`
`{"level": 1, "roster": [{"name","project","owner"}]}`. Superuser-write only,
enforced in the route.

### `bo_audit` — who did what
Every write stamps here **and** into the host application log. Survives log
rotation; this is the record for "who approved that link".

### `bo_ai_usage` — daily AI call counter, enforces `BACKLINK_OPS_AI_DAILY_CAP`

### `bo_schema_version` — applied migrations

## Growth

At the expected rate — two associates, roughly 10–20 links and 3–7 queries each
per working day — the database grows by well under 100 KB a month. SQLite is
comfortable here for years. `docs/SCALING.md` covers the move to Postgres if the
team or the number of sites grows.

## Timezone

The working day is IST (`Asia/Kolkata`). `store.today_ist()` is the only place
that decides what "today" means; nothing else calls `date.today()`.
