# Changelog

Newest first. Production state per feature lives in `docs/FEATURE_LOG.md`.

## 2026-10-26 · Tasks v2, Step 1 database foundation (branch `feat/tasks-v2`), not deployed

- `daily_tracker.db` schema 3: 13 **new** tables (tasks, 15-minute proof, timer intervals, dependency holds, events, corrections,
  leave calendar, settings history, points, badges, employee of the month). No existing table changed.
- Guardrails in the database: v2 rows can never be deleted or replaced, and the trail, proof and points never
  change. Backup taken before the upgrade. Tests: `tests/test_tasks_v2_schema.py` (56).
- Jai's 8 task categories, each with the fields that must be filled in. New website development: 3 working days,
  dependency stops wait for Jai's approval.

## 2026-10-26 · Tasks v2, Step 0 audit (branch `feat/tasks-v2`), no code changed

- Audit of the current `/tasks/` (T4 tracker + T7 task manager), the gap list against the v2 work order, and the
  migration plan (schema 3 in `daily_tracker.db`, behind the new flag `FEATURE_TASKS_V2`). See `docs/TASKS_V2.md`.
  Five open questions for Jai, including the missing master prompt.

## 2026-10-15 · Route registry + task manager (branch `feat/task-manager`), not deployed yet

- **T5:** one route registry (`web/lib/routes.json`) feeds the nav, the SEO tabs and the homepage, which now
  lists every page a person may open, grouped SEO / Content / Team / Finance / Admin, with copyable URLs.
- **T7 (flag `FEATURE_TASK_MANAGER`):** SMART tasks with list / board / calendar views, auto progress from Backlink
  Ops, published blogs, daily logs and ideas; monthly → weekly → daily targets with leave days; Red/Amber/Green
  per task and per person; Mirror page; points ledger, tiers, badges, weekly idea task, monthly payout sheet.
- **Found:** `/invoices/` is not proxied on the dashboard domain, so the desk and client fill links don't open.
  The fix is `ops/fix-invoice-nginx.sh`.

## 2026-10-13 · Dashboard work order (branch `feat/daily-tracker-levels`), not deployed yet

- **Fix (T1):** people rostered on a website now always see it on Backlink Ops, even when it is
  marked not live. The roster matches logins by email, or by name ignoring case. Roster rows that
  match no login are listed for the superuser. whatsappautomation.co.in now ships live.
- **Backlink Ops 1.3.0 (T2, flag `FEATURE_PER_PROJECT_LEVELS`):** level, XP and streak per person
  per website; your Today score is your own links at your own level; superuser grid to set levels.
- **Removed (T3):** the static `/articles/` page (redirects home; archived). Blog publishing unchanged.
- **New (T4, flags `FEATURE_DAILY_TRACKER`, `FEATURE_IDEA_BOARD`):** Daily Tracker at `/tasks/`.
  Proof-backed work logs, review with quality, late = 50%, duplicate block, Backlink Ops rows
  shown automatically, targets, streaks, heatmap, leaderboards, CSV, sheet import. Plus the
  Idea Board with monthly winner badges.
- Homepage Workspace cards and My levels; nav gains Backlink Ops, Daily Tracker, Invoices (admin)
  and a phone row.
