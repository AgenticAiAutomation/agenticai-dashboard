# WhatsApp leads desk

The CRM view over the leads that arrive from the funnel at
**wa.agenticaiautomation.co**. Lives at `/dashboard/leads`.

The funnel collects a lead and decides whether to hand out a WhatsApp link.
This desk is what happens afterwards: who has been contacted, who is on hold,
who converted, who was rejected — and who decided that, when, and why.

## How the two services share one database

There is no second copy of the leads and nothing to keep in sync. The funnel's
SQLite file is read directly:

```
/var/www/wa-funnel/instance/leads.db
```

Both services run as `www-data` on the same box, so the dashboard can open it.
The split of ownership is strict:

| | writes | never touches |
|---|---|---|
| **wa-funnel** | the lead row, once, on submission | `status*`, `lead_status_events` |
| **dashboard** | `status`, `status_note`, `status_by`, `status_at`, and one `lead_status_events` row per change | everything a visitor answered |

The dashboard cannot create, edit or delete a lead. Its listing connection is
opened read-only through a `file:…?mode=ro` URI, so a bug in a read path cannot
write; only `set_status` opens for writing. A test asserts that.

The funnel sets `journal_mode=WAL` on first run, which is what makes this safe:
a listing here does not block a submission arriving there, or the other way
round.

## Turning it on

Off unless the flag is set. Add to `/etc/systemd/system/dashboard-api.service`:

```
Environment="WA_LEADS_ENABLED=1"
Environment="WA_LEADS_DB=/var/www/wa-funnel/instance/leads.db"
Environment="WA_LEADS_WRITE_ROLES=admin,owner,seo_lead,seo"
```

then `systemctl daemon-reload` and `systemctl restart dashboard-api`.

With the flag off, the five endpoints below do not exist and the dashboard is
byte-for-byte what it was. With it on but the funnel not yet deployed, the
endpoints answer **503 with a sentence naming the missing file** — the page
renders and explains itself rather than showing an error.

The dashboard's own settings load from `api/.env` via pydantic and are never
pushed into `os.environ`, so like backlink_ops this module reads plain
`os.environ` and its switches belong in the unit file. See `docs/RUNBOOK.md`.

## Permissions

Reading is open to any signed-in dashboard user. **Writing is not** — a status
is a statement about a real person waiting for a reply, so `WA_LEADS_WRITE_ROLES`
gates it and every change records the actor's email.

`GET /meta` returns `can_write` so the page hides controls it would only get a
403 from, rather than letting someone write a note and then lose it.

## API

All under `/api/wa-leads`, all requiring a dashboard token.

| Method | Path | Notes |
|---|---|---|
| GET | `` | Filter, search, sort, paginate |
| GET | `/stats` | Pipeline counts and conversion rate |
| GET | `/meta` | Statuses, industries, `can_write`, `db_ok` |
| GET | `/{id}` | One lead, with its full status history |
| PATCH | `/{id}/status` | `{ "status": "...", "note": "..." }` |

List query parameters: `status` (a status, or `open` for everything undecided),
`qualified`, `industry`, `search` (name, email or number), `days`, `sort`,
`direction`, `page`, `page_size`.

`sort` is checked against an allowlist before it reaches the `ORDER BY`, which
cannot be parameterised. An unknown value falls back to `created_at`; a test
posts a `DROP TABLE` as the sort key and asserts the listing is unaffected.

## The pipeline

`new → contacted → on_hold → converted | rejected`

Not enforced as a sequence — a lead can go straight from `new` to `rejected`,
because that is what happens. What is enforced is that every move is recorded.

**Conversion rate counts decided leads only** (`converted / (converted +
rejected)`). Leads still in the pipeline are excluded: counting them as "not
yet converted" would make the number fall every time a new lead arrives, which
would be a rate that punishes marketing for working.

## What the page shows that the visitor never sees

The **fit score** is on the table and in the panel. It is hidden from the
visitor and always will be — that is a rule of the funnel — but internally it
is the entire point, so it sorts and filters here.

A lead with **no `consent_at`** is flagged in red and its number is not made
into a `wa.me` link. Without an opt-in on record, messaging that person is not
something we may do, so the UI does not offer it as one click.

The **`ip_hash` is stripped server-side** and never reaches the browser. It
exists for the funnel's rate limiting; a CRM screen has no use for it.

## Tests

```bash
cd api
python tests/wa_leads.py        # store: filters, sorting, statuses, stats
python tests/wa_leads_api.py    # HTTP: shapes, permissions, 404/422/503
```

Both build a throwaway SQLite file with the funnel's schema, so neither needs
Postgres, a token, or a running funnel. `tests/wa_leads.py` carries a copy of
that schema: if wa-funnel changes the shape of its leads table, that is the
test that should start failing.

## If the funnel's schema changes

The columns this module depends on are `status`, `status_note`, `status_by`,
`status_at` and the `lead_status_events` table. They are declared in
wa-funnel's `store.py` — that repo owns the schema, including the tables only
this one writes, so there is one place to read it.

`store.available()` checks those four columns exist before reporting the desk
as usable, so a partial deploy shows a 503 rather than a column error.

## Uninstall

Delete the two lines in `api/app/main.py` and restart. Nothing else references
the module, and no data of the dashboard's own is lost — the leads and their
history live in the funnel's file.
