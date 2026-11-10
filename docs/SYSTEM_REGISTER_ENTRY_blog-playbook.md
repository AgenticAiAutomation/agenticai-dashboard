# SYSTEM_REGISTER entry — Blog Playbook (to merge)

`docs/SYSTEM_REGISTER.md` was not found on 2026-10-05. It is not on any branch
of this repo locally or on GitHub, and not in the AgenticAI-HQ mirror.
AgenticAI-HQ `04-Versions/RELEASES.md` says it came with Dashboard 2.2 on branch
`release/2026-10-02-links-register` (with the Workspace card), and that branch
is not in this clone or on GitHub. Production could not be read from here.
Creating a second copy would conflict with that branch, or, if the file sits on
the server untracked, make `git pull` refuse to run on deploy. So it was **not
created**. Find that branch, or check on the server:

```
ls -l /var/www/agenticai-dashboard/docs/SYSTEM_REGISTER.md
```

If it exists, paste the two blocks below into it (feature row + §10 change log),
then delete this file. If it truly does not exist, rename this file to
`SYSTEM_REGISTER.md` and grow it from here.

## Feature

| Field | Value |
|---|---|
| Feature | Blog Playbook writer (answer-first block writer + advisory Skim score) |
| Status | Built 2026-10-05 on `feat/blog-playbook` (dashboard + AgenticWeb). Not deployed. |
| Flag | `BLOG_PLAYBOOK_ENABLED` (default `false`); `BLOG_PLAYBOOK_USERS` (emails, default empty) |
| New routes | `GET /api/seo/playbook`, `GET /api/seo/articles/{id}/playbook`, `GET /api/seo/articles/{id}/skim` (all read-only) |
| Changed routes | `POST /api/seo/articles`, `PUT /api/seo/articles/{id}/write` (optional `playbook_blocks`); `/generate` (prompt choice); `/publish` (HTML converter choice only — gate unchanged) |
| New column | `seo_articles.playbook_blocks JSONB NULL` — Alembic `003_playbook_blocks` |
| Website | `blog.py` filter `playbook_html`; `blog-post.html`; `static/assets/css/components.css` |
| Users | Jai (admin; first test login), SEO associates (after rollout) |
| Security | Same auth as the existing SEO routes (`seo_user` role). No new secrets, no new external service, no new dependency. Blocks size-capped at 200 KB. The site filter only adds class attributes; it does not change escaping. |
| Guide | `docs/BLOG_PLAYBOOK.md` · rollback: `docs/BCP_AND_ROLLBACK.md` |

## §10 change log row

| Date | Change | Ref | By |
|---|---|---|---|
| 2026-10-05 | Blog Playbook writer added behind `BLOG_PLAYBOOK_ENABLED` (off); skim route, `playbook_blocks` column, site filter. No scoring or publish-gate change. | `feat/blog-playbook` | Claude Code for Jai |

---

## Feature — Blog Playbook v2 (add beside the row above)

| Field | Value |
|---|---|
| Feature | Blog Playbook v2: multi-item sections, one free-label callout, inline WebP upload, bold/links in H2 + FAQ, author Best pick / Notice / Must do, Skim skip, homepage Blog section |
| Status | Built 2026-11-10 on `feat/blog-playbook-v2` (dashboard + AgenticWeb). Not deployed, not pushed. |
| Flag | `BLOG_PLAYBOOK_V2` (default `false`), on top of `BLOG_PLAYBOOK_ENABLED` / `BLOG_PLAYBOOK_USERS` / access file. `ops/blog-playbook-flag.sh v2-on / v2-off` |
| New routes | `POST /api/seo/articles/{id}/upload-inline-image`, `DELETE /api/seo/articles/{id}/inline-image?url=` |
| Changed routes | `GET /api/seo/playbook` (+`v2`), `GET …/playbook` (+`author_extras`), save routes (+`author_extras`), `…/skim` (+`skipped`, `parameters_skipped`), score/publish `blocking_issues` (+Playbook rules, Playbook posts only) |
| New columns | `seo_articles.author_best_pick JSONB NULL`, `author_notice TEXT NULL`, `author_must_do JSONB NULL` — Alembic `004_playbook_author_extras` (down drops only these) |
| Website | `blog.py` (`pb-callout`, `latest()`), `templates/blog-post.html`, `templates/index.html`, `static/assets/css/components.css` |
| Security | Upload validated on the server: real WebP magic bytes + Pillow decode + exactly 1536 × 1024; URL pattern pinned to the article's id before any delete; files written atomically under `SITE_MEDIA_DIR/inline/`. Link scheme filter: only `https://…` and `/…` (no `javascript:`, `data:`, `http:`, `//host`) in builder, renderer and FAQ/author HTML. FAQ answers and author fields are HTML-escaped before bold/links are applied. No new secrets, no new dependency. |
| Guide | `docs/BLOG_PLAYBOOK.md` § v2 · rollback: `docs/BCP_AND_ROLLBACK.md` § Blog Playbook v2 |

## §10 change log row — v2

| Date | Change | Ref | By |
|---|---|---|---|
| 2026-11-10 | Blog Playbook v2 behind `BLOG_PLAYBOOK_V2` (off): bold/link root-cause fix, multi-item sections, inline WebP upload route, one-callout blocker, author extras (migration 004), Skim skip, homepage Blog section. No house-score or publish-gate change. | `feat/blog-playbook-v2` | Claude Code for Jai |
