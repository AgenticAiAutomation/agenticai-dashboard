# Backlink Ops — API

Base: `BACKLINK_OPS_API_PREFIX`, default `/api/seo/backlink-ops`.
Distinct from the dashboard's existing `/api/seo/backlinks` — different feature,
different database, no shared routes.

All responses JSON. Identity comes from whatever the dashboard already
authenticated (JWT cookie or bearer token); the page sends
`credentials: same-origin`.

Errors are `{"error": "<code>", "message": "<sentence for the user>"}`.
`message` is written to be shown as-is; do not rewrite it in the client.

| Code | HTTP | Meaning |
|---|---|---|
| `not_authenticated` | 401 | No dashboard session. Client reloads to the login page. |
| `forbidden` | 403 | Authenticated, but not superuser. |
| `read_only_user` | 403 | Dashboard role maps to `viewer` — reads fine, writes refused. |
| `read_only` | 503 | `BACKLINK_OPS_READ_ONLY=1` — maintenance. Reads still work. |
| `invalid` | 400 | Bad input; `message` says what to fix. |
| `not_found` | 404 | Entry already gone. |

---

### `GET /health` — no auth
Deploy gate and monitor probe. `200` with `db_ok:true`, else `503`.
```json
{"feature":"backlink-ops","version":"1.0.0","schema":1,"enabled":true,
 "read_only":false,"db":"/var/www/.../instance/backlink_ops.db","db_ok":true,
 "ai":"rules-only","ai_calls_today":0}
```

### `GET /bootstrap` — any user
Everything the page needs once: `me` (with `role`), `config`, `levels`, `level`,
`linkTypes`, `projects`, `seedKeywords`, `today`, `readOnly`, `aiEnabled`.

### `GET /day?project=&date=` — any user
The scored day. `rows[]` each carry server-computed `pts`, `flags[]`, `tier`,
`status`, `note`. Plus `points`, `counted`, `queries`, `avgDa`, `high`,
`rejected`, `reqs[]`, `done`, `band`, `target`, `level`, `coach`.

`reqs[]` is the checklist the associate must clear: `{k, ok, label, now}`.
`done` is true only when every `ok` is true — that is what fires the confetti.

### `POST /entries` — any user · 201
Body: `project, url, type, da, spam, follow, target, anchor, kw, relevant, indexed`.
Returns the recomputed day. `id`, `date`, `author`, `host` are set server-side
and ignored if sent.

### `DELETE /entries/<id>?project=` — any user
Returns the recomputed day. An approved entry can still be deleted by the person
who logged it; the deletion is audited.

### `POST /analyse` — any user
Body: `project, kw, pasted, skip?`. Runs the keyword verdict (AI if configured,
deterministic rules otherwise), writes the bank row and the query row.
Returns `{analysis, day, bank}`. `analysis._source` is the provider name or
`"rules"` — surface it, so nobody mistakes a fallback for a model's judgement.

### `GET /bank?project=` — any user

### `POST /coach` — any user
Body: `{project}`. Grades today's sheet. `400 empty` when nothing is logged.

### `POST /review` — **superuser**
Body: `{project, decisions:[{id, status, note?}]}`, batch-capable.
`status` ∈ `approved|rejected|needs_fix|pending`. Returns the recomputed day.

### `GET /board?days=14` — any user
`series[]` of `{author, project, date, points, queries, done}`, plus `level`,
`roster`, `bankCounts`, `today`.

### `GET /config` — any user · `PUT /config` — **superuser**
PUT accepts `level` (1–5) and/or `roster`. Rejected if the roster would leave
nobody as superuser — you cannot lock yourself out through the UI.

### `GET /audit?limit=200` — **superuser**
### `POST /ai-selftest` — **superuser**
One live round-trip to the configured provider. `200 {"ok":true,...}` or
`502 {"ok":false,"detail":"..."}` naming what failed (bad key, wrong model id,
reply without JSON). **Run this after changing provider or model** — in normal
use a broken provider is invisible, because verdicts quietly fall back to rules.

### `POST /backup` — **superuser**
Online SQLite backup, prunes to the newest 30. Returns the path written.

---

## Adding an endpoint

1. Route in `blueprint.py`, under `api_bp`, with `@require_user` (and
   `@require_superuser` / `@require_writable` as appropriate).
2. `audit.stamp_request(...)` on any write. No exceptions.
3. Validate input and return a `message` a person can act on.
4. Document it here and add a line to `docs/FEATURE_LOG.md`.
