# SYSTEM_REGISTER entry — Daily Tracker, per-site levels, /articles removal (to merge)

`docs/SYSTEM_REGISTER.md` is still not in this repo or on GitHub (see
`SYSTEM_REGISTER_ENTRY_blog-playbook.md`). Paste the blocks below into it on the server,
or merge them when the register branch turns up, then delete this file. No secret values below.

## Features

| Field | Value |
|---|---|
| Feature | Per-person, per-site levels on Backlink Ops (v1.3.0) |
| Flag | `FEATURE_PER_PROJECT_LEVELS` (default off) |
| Data | `backlink_ops.db` table `bo_user_levels` (schema 1 → 2, additive); meta key `levels_v2_migration` |
| Routes | `GET /api/seo/backlink-ops/levels`, `GET …/levels/all` (superuser), `PUT …/levels` (superuser) |
| Not flagged | Roster ↔ login matching by email / case-insensitive name; "not live" sites visible to people rostered on them; roster email column |

| Field | Value |
|---|---|
| Feature | Daily Tracker + Idea Board at `/tasks/` (v1.0.0, `api/app/daily_tracker/`) |
| Flags | `FEATURE_DAILY_TRACKER`, `FEATURE_IDEA_BOARD` (default off; both off = not mounted, old task list shown) |
| Data | Own SQLite `api/instance/daily_tracker.db`: `work_types`, `daily_logs`, `user_targets`, `ideas`, `idea_votes`, `user_badges`, `dt_people` |
| Routes | `/api/tasks/*` (status, work-types, logs, review, review-bulk, review-queue, summary, report, export.csv, import, settings, targets), `/api/ideas/*` |
| Env | `DAILY_TRACKER_DB`, `DAILY_TRACKER_BACKUP_DIR`, optional `DAILY_TRACKER_SUPERUSERS` (defaults to `BACKLINK_OPS_SUPERUSERS`), `DAILY_TRACKER_ADMIN_ROLES` (owner,admin), `DAILY_TRACKER_USER_HOOK`, `DAILY_TRACKER_READ_ONLY` |
| Users / roles | All logins with a Backlink Ops roster row log work; owner/admin + superuser emails review. Akash (`akash0710yadav@gmail.com`) needs a roster row with that email on WA Auto. |
| Security | Same bearer-token hook as Invoice Desk. No new secret, dependency or external service. Pay amounts are not stored. |

| Field | Value |
|---|---|
| Removed | Static `/articles/` page → redirect to `/`. Archived in `archive/removed_2026-10-13/`. API and blog publishing unchanged. |
| Nav / homepage | Nav: Articles removed, Tasks → Daily Tracker, + Backlink Ops, + Invoices (admin), mobile row. Homepage: Workspace cards + My levels. |

## §10 change log rows

| Date | Change | Ref | By |
|---|---|---|---|
| 2026-10-13 | T1: Akash couldn't see whatsappautomation.co.in. Root cause: site shipped inactive and was hidden even from rostered people; roster matched logins by exact case-sensitive display name. Fixed for all users (email/case-insensitive match, rostered sites always visible, unmatched rows shown to superuser). | `feat/daily-tracker-levels` | Claude Code for Jai |
| 2026-10-13 | T2: per-(user, site) levels behind `FEATURE_PER_PROJECT_LEVELS` (off); global level carried over. | same | Claude Code for Jai |
| 2026-10-13 | T3: static `/articles/` page removed (archived, redirect). Publishing untouched. | same | Claude Code for Jai |
| 2026-10-13 | T4: Daily Tracker + Idea Board behind `FEATURE_DAILY_TRACKER` / `FEATURE_IDEA_BOARD` (off). | same | Claude Code for Jai |
