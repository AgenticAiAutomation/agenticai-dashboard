# SYSTEM_REGISTER entry — Tasks v2 (to merge)

`docs/SYSTEM_REGISTER.md` is still not in the repo. Merge the blocks below into it, then delete this file.
No secret values. Updated after each step of `TASKS_V2_CLAUDE_CODE_STEPS.md`.

## Links

| Group | Page | URL | Who | Status |
|---|---|---|---|---|
| Team | Task timer | `https://dashboard.agenticaiautomation.co/tasks/?tab=timer` | everyone (when `tasksV2` is on) | built, not deployed |

API: `/api/tasks/v2/*` (state, tasks, start, pause, session/end, complete, block, unblock, holds/{id}/decide, proof).

## Features

| Feature | State | Where |
|---|---|---|
| Tasks v2 schema 3: work tasks (8 categories with required fields), timer intervals, dependency holds (Jai approves), 15-minute proof, events, corrections, leave calendar, settings history, points, badges, employee of the month | built 26 Oct 2026, **not deployed** | `api/app/daily_tracker/store.py` (`SCHEMA_3`, `_migrate_v3`) |
| Task timer, 15-minute proof, road blockers with next-task suggestions (flag `FEATURE_TASKS_V2`) | built 26 Oct 2026, **not deployed** | `api/app/daily_tracker/worktime.py`, `web/components/worktime/TimerPanel.tsx` |

## Users and roles

Unchanged. Superuser = emails in `DAILY_TRACKER_SUPERUSERS`. Admin = dashboard roles in `DAILY_TRACKER_ADMIN_ROLES`.

## Credentials (names only)

No secrets. New environment flag: `FEATURE_TASKS_V2` (default off), written by `daily-tracker-flags.sh v2`.

## Security status

- Database-level guardrails: no v2 row can be deleted or replaced. The audit trail, 15-minute proof, points and
  awards are write-once.
- Privacy: only explicit task events. No keystrokes, screenshots, browsing history, audio or video.

## §10 change-log row

| Date | Change | By | Rollback |
|---|---|---|---|
| 2026-10-26 | Tasks v2 Step 2: task timer tab behind FEATURE_TASKS_V2 | Claude Code for Jai | `daily-tracker-flags.sh off`, or previous commit |
| 2026-10-26 | Tasks v2 Step 1: daily_tracker.db schema 3 (new tables only), backup before upgrade | Claude Code for Jai | restore `backups/daily_tracker/*-pre-v3.db`, or leave the tables (old code ignores them) |
