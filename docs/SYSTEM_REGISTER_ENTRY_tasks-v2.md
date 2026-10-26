# SYSTEM_REGISTER entry — Tasks v2 (to merge)

`docs/SYSTEM_REGISTER.md` is still not in the repo. Merge the blocks below into it, then delete this file.
No secret values. Updated after each step of `TASKS_V2_CLAUDE_CODE_STEPS.md`.

## Links

No new page yet. The v2 screens live under `https://dashboard.agenticaiautomation.co/tasks/` and get registry
entries (nav + Workspace card) in the step that builds them.

## Features

| Feature | State | Where |
|---|---|---|
| Tasks v2 schema 3: work tasks, timer intervals, 15-minute proof, events, corrections, leave calendar, settings history, points, badges, employee of the month | built 26 Oct 2026, **not deployed** | `api/app/daily_tracker/store.py` (`SCHEMA_3`, `_migrate_v3`) |

## Users and roles

Unchanged. Superuser = emails in `DAILY_TRACKER_SUPERUSERS`. Admin = dashboard roles in `DAILY_TRACKER_ADMIN_ROLES`.

## Credentials (names only)

None new.

## Security status

- Database-level guardrails: no v2 row can be deleted or replaced. The audit trail, 15-minute proof, points and
  awards are write-once.
- Privacy: only explicit task events. No keystrokes, screenshots, browsing history, audio or video.

## §10 change-log row

| Date | Change | By | Rollback |
|---|---|---|---|
| 2026-10-26 | Tasks v2 Step 1: daily_tracker.db schema 3 (new tables only), backup before upgrade | Claude Code for Jai | restore `backups/daily_tracker/*-pre-v3.db`, or leave the tables (old code ignores them) |
