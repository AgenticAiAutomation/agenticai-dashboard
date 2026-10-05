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
