# Backlink Ops — scaling

Written so the next change is obvious rather than archaeological. Each section
says **the signal**, **the move**, and **what it costs**.

## Where the current design runs out

| Dimension | Comfortable now | First strain |
|---|---|---|
| Associates | 2–10 | ~25 concurrent writers (SQLite writer lock) |
| Sites | 2 | any number — `seed.PROJECTS` is a dict |
| Entries | hundreds of thousands | `/board` re-scores in Python; slow past ~50k rows in the window |
| Keywords | thousands | fine |
| AI calls | capped daily | provider rate limits |

## 1. Adding a third site

**Signal:** a new client site needs its own off-page desk.
**Move:** one entry in `seed.PROJECTS` and one list in `seed.SEED_KEYWORDS`. Pick
a hue that passes contrast in both themes — the two current hues (`#00998C`,
`#B85520`) were validated for colour-blind separation; run any third through the
same check before shipping.
**Cost:** nothing. No migration, no code change elsewhere.

## 2. Adding a keyword cluster to an existing site

Append to `seed.SEED_KEYWORDS[project]`. The Keyword Lab serves the first seed
keyword not yet in `bo_bank`, so new entries queue up automatically behind the
finished ones.

## 3. Changing the scoring formula

**Signal:** the ladder stops discriminating — everyone maxes out, or nobody
clears it.
**Move:** edit `scoring.py`, update `tests/test_scoring.py` to the new expected
numbers, and **stamp `docs/FEATURE_LOG.md`**. Because points are recomputed and
never stored, the change applies to history too — which is usually what you want,
and always worth telling the associates before it lands.
**Cost:** none technically. Politically, never change it mid-week.

## 4. Moving off SQLite

**Signal:** more than ~25 people writing at once, or you want to join this data
against the main dashboard's tables.
**Move:**
1. `migrations/001_backlink_ops_up.sql` is close to portable — swap
   `INTEGER PRIMARY KEY AUTOINCREMENT` for `BIGSERIAL`, `TEXT` timestamps for
   `TIMESTAMPTZ`.
2. Rewrite `store.py` only. It is the single module that touches SQL;
   `scoring.py`, `blueprint.py` and the template do not know what the database
   is.
3. Keep the `bo_` prefix so the tables stay recognisable in a shared database.
**Cost:** roughly a day, one module, no UI change.

## 5. Faster scoreboard

**Signal:** `/board` takes more than a second.
**Move:** a `bo_daily_rollup(author, project, date, points, queries)` table
written on entry/review change, with `/board` reading it directly. Keep the
recompute path as the source of truth and rebuild the rollup from it — never let
the rollup become the only copy.

## 6. Ubersuggest via API instead of paste

**Signal:** the paste step becomes the bottleneck, or you buy API access.
**Move:** add a provider in `ai.py` alongside the LLM adapters, fill `volume/kd/
cpc` from it, and keep the paste box as the fallback. Do not remove the paste
path — it is what works when the API quota is gone.

## 7. Notifications

**Move:** read `bo_audit` on a schedule and push to WhatsApp — the audit stream
already carries actor, action and detail. Send on: target cleared, link
rejected, no entries logged by 4pm IST. Do not put the sender inside the request
path; a slow webhook must never slow the desk.

## 8. Multi-tenant

**Signal:** you sell this desk to clients.
**Move:** a `tenant` column on every `bo_` table, resolved from the host's
session, and a rule in `auth.py`. Design for it before the second tenant, not
after — retrofitting tenancy across seven tables is the expensive version.

## Things to leave alone

- **Points are never stored.** Caching them creates two generations of numbers.
- **The AI never scores.** The moment a model decides the target, the number is
  no longer auditable.
- **`store.today_ist()` is the only definition of "today".** Do not add a second.
