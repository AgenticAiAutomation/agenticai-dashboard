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
PUT accepts any of `level` (1–5), `roster`, `levels` and `projects`. Rejected if
the roster would leave nobody as superuser — you cannot lock yourself out
through the UI.

- `levels` (v1.1): `{"1": {"target": 300, "min_links": 40, "queries": 3,
  "min_avg_da": 20, "high_value": 0}, ...}` — only those five fields, bounded;
  `{}` restores the shipped ladder.
- `projects` (v1.1): a list of `{id, name, short, domain, pages, niche,
  keywords, active}`. Seed sites may be edited but never removed; a new site
  needs `id`, `name` and `domain`. `pages` accepts a list or a comma string.

### `POST /auto-review` — **superuser**, or cron with `X-Backlink-Ops-Cron`
(v1.1) One automatic review pass over every pending link; see RUNBOOK
"Automatic review". Returns `{"run": {checked, approved, sent_back, flagged,
ai, seconds, ...}}`. The header must equal `BACKLINK_OPS_CRON_SECRET` (compared
in constant time); with the secret unset only a superuser can trigger it.

### `GET /auto-review` — **superuser**
(v1.1) `{"last": <summary of the last run>, "enabled", "ai", "pending"}`.

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

## v1.2 — all projects

`GET /api/seo/backlink-ops/progress?days=14` (any signed-in desk user)
→ `{rows:[{project,date,author,links,approved,pending,needs_fix,rejected,points,queries,done}], level, days, today, projects, roster}`

## Invoice Desk — `/api/invoices` (superuser only unless marked public)

| Method | Path | Does |
|---|---|---|
| GET | `/health` | public health |
| GET | `/bootstrap` | settings, counts, states, catalog |
| GET | `/list?view=queue\|issued\|void\|all` | invoice summaries |
| POST | `/new` | blank draft |
| POST | `/totals` | live totals for the editor |
| GET/PUT/DELETE | `/inv/{id}` | read / save draft / delete draft |
| POST | `/inv/{id}/issue` | number + lock (body = latest edits) |
| POST | `/inv/{id}/void` | `{reason}` |
| POST | `/inv/{id}/duplicate` | new draft from any invoice |
| GET | `/inv/{id}/pdf` | PDF (DRAFT watermark until issued) |
| GET/PUT | `/settings` | seller, bank, numbering, defaults |
| GET/POST | `/links` · DELETE `/links/{token}` | fill links |
| GET | `/audit` | audit trail |
| GET/POST | `/public/{token}` | **public** — form meta / submit |

## Blog Playbook — `/api/seo` (SEO login; flagged)

Off unless `BLOG_PLAYBOOK_ENABLED=true` or the caller's email is in
`BLOG_PLAYBOOK_USERS`. All three are read-only and live in
`app/seo/routes/playbook.py`. Guide: `docs/BLOG_PLAYBOOK.md`.

| Method | Path | Does |
|---|---|---|
| GET | `/api/seo/playbook` | `{enabled}` for the calling login |
| GET | `/api/seo/articles/{id}/playbook` | `{article_id, playbook_blocks}`; 404 when off |
| GET | `/api/seo/playbook/access` | **Admin.** `{everyone, emails, server_enabled, server_emails, users[{id,email,full_name,role,granted,via_server,enabled}]}` |
| PUT | `/api/seo/playbook/access` | **Admin.** Body `{everyone, emails[]}`. Emails must be active logins that can write articles (else 422). Audit-logged as `seo.playbook.access_changed`. |
| GET | `/api/seo/articles/{id}/skim` | Advisory skim score: `{total_score, max_score: 100, advisory: true, note, checks[]}`; 404 when off. Same auth as `/score`. Never read by publish. |

Changed, additively:

- `POST /api/seo/articles` and `PUT /api/seo/articles/{id}/write` accept an
  optional `playbook_blocks` object (≤ 200 KB, else 422). It is stored as-is when
  on and ignored when off.
- `POST /api/seo/articles/generate` uses the Playbook prompt when on and stores
  the model's `playbook_blocks`.

### Playbook v2 (`BLOG_PLAYBOOK_V2`, on top of the Playbook access above)

| Method | Path | Does |
|---|---|---|
| POST | `/api/seo/articles/{id}/upload-inline-image` | Multipart `file`. Must be a real WebP (bytes `RIFF....WEBP`, Pillow agrees) of exactly 1536 × 1024, else **400** `"Upload a WebP image of exactly 1536 × 1024."` Stored via `storage.put_object` (key `<article_id>/<token>.webp`) plus a public copy in `SITE_MEDIA_DIR/inline/`. Returns `{url, bytes}` — `url` is `/static/blog/inline/<article_id>-<token>.webp` for `![alt](url)`. Never touches `featured_image_path`. Audit `seo.article.inline_image_uploaded`. 404 when v2 is off. |
| DELETE | `/api/seo/articles/{id}/inline-image?url=` | Removes both files for an inline image of **this** article (else 422). On a published article the files are kept (`file_removed: false`) until the next publish. Audit `seo.article.inline_image_removed`. |

Changed, additively (only with v2 on for the caller):

- `GET /api/seo/playbook` adds `"v2": true`. With v2 off the key is absent.
- `GET /api/seo/articles/{id}/playbook` adds `author_extras`
  `{best_pick: {option, reason} | null, notice | null, must_do: [..] | null}`.
- `POST /api/seo/articles` and `PUT /api/seo/articles/{id}/write` accept an
  optional `author_extras` object (same shape; must_do ≤ 5, each field
  ≤ 2,000 chars, else 422). `playbook_blocks` may now be `version: 2`.
- `GET /api/seo/articles/{id}/skim`: checks may carry `skipped: true` (0 of
  0); the response adds `parameters_skipped`.
- Score / publish `blocking_issues` add the Playbook rules for Playbook posts
  (callout 0 / > 1, real example with no numbers, inline image without alt,
  link that is not `https://…` or `/…`).
- Publish file (`schema_version` still 1): each FAQ may carry `answer_html`
  (then `answer` is plain text, for the FAQPage JSON-LD); optional
  `author_extras {best_pick: {option, reason_html}, notice_html, must_do_html[]}`.

## Article HTML export — `/api/seo/articles` (SEO login)

| Method | Path | Does |
|---|---|---|
| GET | `/api/seo/articles/{id}/export.html` | The article as one self-contained HTML file (`Content-Disposition: attachment; filename="<slug>.html"`). **409** `below_threshold` unless the stored house score is at least 80 (`PUBLISH_MIN_SCORE`). Reads the body the scorer reads, converts it as publishing does, embeds the featured image, adds FAQs and From the author. Light only, no scripts. Audit-logged as `seo.article.exported_html`. Not behind the Playbook flag. |
