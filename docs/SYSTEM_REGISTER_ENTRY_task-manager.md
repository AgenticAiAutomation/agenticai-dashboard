# SYSTEM_REGISTER entry — route registry (T5) + task manager (T7) (to merge)

`docs/SYSTEM_REGISTER.md` is still not in the repo (see `SYSTEM_REGISTER_ENTRY_blog-playbook.md`).
Merge the blocks below into it, then delete this file. No secret values.

## Links (generated from `web/lib/routes.json`, 15 Oct 2026)

The registry is the source of truth: the homepage and nav read it, and
`tests/test_route_registry.py` fails if a page is missing from it. Update the registry, not this table.

| Group | Page | URL | Who | Status |
|---|---|---|---|---|
| SEO | SEO Operations | `https://dashboard.agenticaiautomation.co/dashboard/seo/` | everyone | live |
| SEO | Inbox | `https://dashboard.agenticaiautomation.co/dashboard/seo/inbox/` | everyone | live |
| SEO | Backlinks (site profile) | `https://dashboard.agenticaiautomation.co/dashboard/seo/backlinks/` | everyone | live |
| SEO | Recommendations | `https://dashboard.agenticaiautomation.co/dashboard/seo/recommendations/` | everyone | live |
| SEO | Technical audit | `https://dashboard.agenticaiautomation.co/dashboard/seo/technical-audit/` | everyone | live |
| SEO | Keywords | `https://dashboard.agenticaiautomation.co/keywords/` | everyone | live |
| SEO | Countries | `https://dashboard.agenticaiautomation.co/countries/` | everyone | live |
| SEO | Backlink Ops | `https://dashboard.agenticaiautomation.co/seo/backlink-ops/` | everyone | live |
| Content | Content calendar | `https://dashboard.agenticaiautomation.co/dashboard/seo/calendar/` | everyone | live |
| Content | Articles | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/` | everyone | live |
| Content | New article | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/new/` | owner, admin, seo, seo_lead | live |
| Content | Scoring guide | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/scoring-guide/` | everyone | live |
| Content | Playbook guide | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/scoring-guide/#blog-playbook` | everyone | hidden |
| Content | Write an article | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/write/` | owner, admin, seo, seo_lead | hidden |
| Content | Edit article | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/edit/` | owner, admin, seo, seo_lead | hidden |
| Content | Author review | `https://dashboard.agenticaiautomation.co/dashboard/seo/articles/author-review/` | everyone | hidden |
| Content | Blog Gate | `https://dashboard.agenticaiautomation.co/blog-gate/` | everyone | planned |
| Content | Articles (old list) | `https://dashboard.agenticaiautomation.co/articles/` | everyone | removed |
| Team | Dashboard | `https://dashboard.agenticaiautomation.co/dashboard/` | everyone | live |
| Team | Backlink scoreboard | `https://dashboard.agenticaiautomation.co/seo/backlink-ops/#board` | everyone | live |
| Team | Tasks & Daily Tracker | `https://dashboard.agenticaiautomation.co/tasks/` | everyone | live |
| Team | Idea Board | `https://dashboard.agenticaiautomation.co/tasks/?tab=ideas` | everyone (when `ideas` is on) | live |
| Team | Mirror | `https://dashboard.agenticaiautomation.co/tasks/?tab=mirror` | everyone (when `taskManager` is on) | live |
| Team | Team | `https://dashboard.agenticaiautomation.co/dashboard/seo/team/` | everyone | live |
| Team | My account | `https://dashboard.agenticaiautomation.co/account/password/` | everyone | live |
| Finance | Invoices | `https://dashboard.agenticaiautomation.co/invoices/` | owner, admin | live |
| Admin | Users | `https://dashboard.agenticaiautomation.co/settings/users/` | owner, admin | live |
| Admin | Backlink Ops settings | `https://dashboard.agenticaiautomation.co/seo/backlink-ops/#settings` | owner, admin | live |
| Admin | Review queue | `https://dashboard.agenticaiautomation.co/tasks/?tab=review` | owner, admin (when `tracker` is on) | live |
| Admin | Targets & rewards | `https://dashboard.agenticaiautomation.co/tasks/?tab=plan` | owner, admin (when `taskManager` is on) | live |
| Admin | Tracker report & settings | `https://dashboard.agenticaiautomation.co/tasks/?tab=report` | owner, admin (when `tracker` is on) | live |
| Admin | Log in | `https://dashboard.agenticaiautomation.co/login/` | everyone | hidden |

API-only pages, proxied by nginx on the dashboard domain: `/seo/backlink-ops/`, `/invoices/` (+ the client fill
links `/invoices/f/<token>`). **15 Oct:** `/invoices/` was found NOT proxied on the dashboard domain. The fix is
`ops/fix-invoice-nginx.sh`.

## Features

| Field | Value |
|---|---|
| Feature | Route registry (T5). One file: `web/lib/routes.json` → nav, SEO tabs, homepage grid (grouped, role-filtered, copyable URLs). |
| Flag | none (pure frontend; flagged entries hide until their flag is on) |

| Field | Value |
|---|---|
| Feature | Task manager (T7), `api/app/daily_tracker/taskmgr.py`, Daily Tracker module v1.1.0 |
| Flag | `FEATURE_TASK_MANAGER` (default off) |
| Data | `daily_tracker.db` schema 2: `tasks`, `task_assignees`, `task_checklist`, `task_links`, `task_progress`, `task_comments`, `task_targets` (the spec's `user_targets`, renamed: T4 already uses that name), `target_splits`, `role_templates`, `leave_days`, `points_ledger`, `reward_tiers`, `rag_settings`, `reward_months`; new columns `ideas.week/test_plan/effort`, `daily_logs.rework`. `backlink_ops.db`: `bo_level_bonus`. Reads `seo_articles` (Postgres) read-only for blog progress. |
| Env | `FEATURE_TASK_MANAGER`, optional `TASK_MANAGER_WORKDAYS` (default `0,1,2,3,4,5` = Mon–Sat) |
| Routes | `/api/tasks/items[...]`, `/people`, `/plan[/split,/template]`, `/templates`, `/leave[/remove]`, `/rag[/team]`, `/rag-settings`, `/mirror`, `/mirror-settings`, `/tiers`, `/rewards[/approve]`, `/rewards.csv` |
| Roles | Jai (superuser email): everything, incl. tiers, bonus notes, rank switch, payout approval. owner/admin: create/assign/approve tasks, targets, thresholds. seo_lead: own tasks, progress, ideas, own Mirror. viewer: reads own tasks only. |
| Security | No pay amounts on people; tier bonus is a note on the tier, shown only to that person and admins. Same bearer-token hook. |

## §10 change log rows

| Date | Change | Ref | By |
|---|---|---|---|
| 2026-10-15 | T5: route registry; homepage lists every live page by group and role; nav reads it. | `feat/task-manager` | Claude Code for Jai |
| 2026-10-15 | T7: task manager behind `FEATURE_TASK_MANAGER` (off): SMART tasks, auto progress, targets, RAG, Mirror, points/tiers, weekly idea. | `feat/task-manager` | Claude Code for Jai |
| 2026-10-15 | Found: `/invoices/` not proxied on dashboard.agenticaiautomation.co (desk + client fill links bounce to the dashboard). Fix script staged. | `ops/fix-invoice-nginx.sh` | Claude Code for Jai |
