# Blog Visual Engine — runbook

Two apps, one flag each, one directory between them. Every step below is
reversible and the first rollback is always "turn the flag off".

| | dashboard API | marketing site |
|---|---|---|
| repo | agenticai-dashboard, `/var/www/agenticai-dashboard` | AgenticWeb, `/var/www/agenticai` |
| service | `dashboard-api` (uvicorn :5004, `www-data`) | `agenticai` (gunicorn :5001, root) |
| flag | `BLOG_ENGINE_V2=true` in `api/.env` / the unit | `BLOG_ENGINE_V2=true` in the unit's environment |
| what the flag does | enables `/api/seo/articles/{id}/blocks*`, `/api/seo/media/upload`, the Blocks link | serves `published/articles/<slug>/index.html` when it exists |
| off | endpoints 404, editor link hidden, publisher writes legacy JSON only | ignores `index.html` files; legacy path for everything |

The two flags are independent. The API can be on with the site off: block
articles publish their JSON record and the site renders them through the
legacy template from the `html` field (the rendered body). Turning the site
flag on then switches those URLs to the pre-rendered page.

## First deploy of the engine (Phase 2)

Order matters only in that the migration must run before the API restarts.

1. **Database** — additive, reversible. On the dashboard box:
   `cd /var/www/agenticai-dashboard/api && ./venv/bin/alembic upgrade head`
   (deploy.sh does this). Adds `content_blocks`, `content_format` to
   `seo_articles` and the `seo_article_revisions` table. Nothing existing changes.
2. **Dependency** — `nh3` is in requirements.txt; `pip install -r` picks it up.
3. **Writable directories** — the API writes `published/articles/<slug>/` and
   `published/media/uploads/`, `published/media/engine/`. `published/` is
   already owned by `www-data`; nothing new to create.
4. **Restart** `dashboard-api`. With the flag still off, nothing is visible.
5. **Turn the API flag on** (`BLOG_ENGINE_V2=true`), restart. The Blocks link
   appears for everyone; publishing block articles writes `index.html`.
6. **Site**: pull `main` (after the site branch merges), set `BLOG_ENGINE_V2=true`
   in the `agenticai` unit, restart. Pre-rendered pages now serve as files.
7. **nginx, one header** — the editor preview loads the site's fonts from the
   dashboard origin. Add to the site's server block:

   ```
   location /static/assets/fonts/ { add_header Access-Control-Allow-Origin "*"; expires 1y; }
   ```

   Without it the preview falls back to metric-matched system fonts; the
   published page is unaffected.

Verify: `curl -I https://agenticaiautomation.co/blog/<a-legacy-slug>` still
200 with the legacy markup; the dashboard Articles list shows **Blocks**.

## Everyday operations

**Migrate one legacy article** (never bulk):

```
./venv/bin/python -m scripts.migrate_article_to_blocks <slug>          # dry run, prints diff + notes
./venv/bin/python -m scripts.migrate_article_to_blocks <slug> --apply  # write blocks, revision 1
```

Then open it in the block editor, fix what NOTES lists (usually a table
caption), and publish from the dashboard. The markdown columns are untouched.

**Site chrome or tokens changed** (nav, footer, `design_tokens.json`, a
renderer fix): re-render every published block article —

```
./venv/bin/python -m scripts.rerender_all --dry-run
./venv/bin/python -m scripts.rerender_all
```

Seconds. Pages update on the next request; IndexNow is told.

**Author details** (name, title, bio, photo, LinkedIn, credentials) are
`BLOG_AUTHOR_*` in `api/.env`. Change, restart, re-render.

**Regenerate the block reference** after a schema change:
`python -m scripts.gen_block_schema_doc`.

## Rollback ladder

1. **Flag off on the site** → every URL serves the legacy template again
   (block articles from their JSON `html`). Seconds. Data kept.
2. **Flag off on the API** → editor hidden, endpoints 404. Data kept; block
   articles remain `content_format=blocks` and can still be scored/published
   through the old endpoints from their markdown projection.
3. **Schema** → `python -m scripts.rollback_blocks --confirm` (or
   `alembic downgrade 002`). Drops only what 003 added. Block content is
   lost; markdown is not.
4. **Files** → `rm -rf published/articles/<slug>/` removes one pre-rendered
   page; the JSON record beside it keeps the URL alive through the legacy path.
5. **Everything** → tarballs + DB dump in `/var/backups/blogengine/`, restore
   rehearsed on 2026-09-18.

Target time for step 1: under a minute. Log any use of steps 3–5 in
`docs/FEATURE_LOG.md` with cause and time to recover.

## Common failures

| symptom | cause | fix |
|---|---|---|
| Blocks link missing | API flag off, or the frontend build predates Phase 2 | `GET /api/seo/blog-engine/status` → `enabled` |
| Save says "Not saved" naming a block | schema rejection (alt text, caption, id…) | the message names the field; fix it in that block |
| Publish 409 `validators_blocking` | a ⛔ check | fix it, or admin override with a reason (audited) |
| Publish 409 `score_below_threshold` | under 80 | Save & score; the gate cannot be overridden |
| Publish 409 `blocking_issues` | no featured image / alt / author story | same as the legacy editor |
| Preview in system fonts | fonts blocked cross-origin | the nginx header above |
| Published page unstyled below the fold | `published/media/engine/*.css` missing or nginx `/static/blog/` alias broken | `python -m scripts.rerender_all`; check the alias |
| 500s after a Postgres restart | stale pool | fixed: `pool_pre_ping` on the engine (Phase 2) |
| Legacy article with a markdown table renders as pipes | `_normalise_markdown` splits table rows (pre-existing) | migrate the article to blocks; the converter re-joins rows |

## Test environment

A disposable database `agenticai_dashboard_test` (owner `dash_test`) exists
on the VPS beside production. Tunnel it (`ssh -L 15432:localhost:5432`), run
`alembic upgrade head` against it, start a local API on :5005 with
`BLOG_ENGINE_V2=true` and scratch `SITE_CONTENT_DIR`/`SITE_MEDIA_DIR`, then:

```
python -m tests.blog_engine        # 86 offline checks, no DB
python -m tests.blog_engine_api    # 49 checks over HTTP
```

Never point a test API at `agenticai_dashboard`; the API suite creates and
deletes articles and users.
