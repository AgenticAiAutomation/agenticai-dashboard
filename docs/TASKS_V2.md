# Tasks v2 — time-based tasks, targets and gamification

Work order: `TASKS_V2_CLAUDE_CODE_STEPS.md` (14 steps, one at a time). Branch `feat/tasks-v2`, cut from
`feat/task-manager` (the branch that is live). Nothing here is pushed until Jai says so.

---

## Current state (Step 0 audit, 26 Oct 2026, no code changed)

### What `/tasks/` is today

`/tasks/` is one Next.js page (`web/app/tasks/page.tsx`) that switches on the API's flags
(`GET /api/tasks/status`). If that endpoint answers 404 (all flags off), it shows the **old task list**
(`web/components/LegacyTasks.tsx` → Postgres `tasks` via `/tasks`, `api/app/routes/tasks.py`).

| Tab | Shown when | Built in | What it does |
|---|---|---|---|
| My tasks (list / board / calendar) | `FEATURE_TASK_MANAGER` | T7, 15 Oct | SMART tasks: all fields required, status flow todo → in progress → submitted → approved / needs fix, blocked |
| Daily log / Today | `FEATURE_DAILY_TRACKER` | T4, 13 Oct | Proof-backed work log, marks per work type, review with quality 1–5 |
| Progress & leaderboard | tracker | T4 | Heatmap, streak, leaderboards |
| Idea Board | `FEATURE_IDEA_BOARD` | T4 | Ideas, votes, monthly winner badge |
| Mirror | task manager | T7 | Target vs actual RAG, points, tier, badges, rank |
| Review queue | admin + tracker / task manager | T4 | Approve logs and ideas |
| Targets & rewards | admin + task manager | T7 | Monthly targets per person, site and unit; leave days; RAG thresholds; tiers; payout sheet |
| Report & settings | admin + tracker | T4 | Report, CSV, sheet import, work types, marks targets |

The flags are switched with `/root/daily-tracker-flags.sh` (systemd drop-in `dashboard-api.service.d/daily-tracker.conf`).
**I can't see which flags are on in production from here.** The Follow-ups flag has been on since 22 Oct.

### Where the data lives

- **`instance/daily_tracker.db`** (SQLite, module `api/app/daily_tracker/`, schema version 2). This is where v2 goes.
  Tables: `work_types`, `daily_logs`, `user_targets` (marks/day), `ideas`, `idea_votes`, `dt_people`,
  `user_badges`, `tasks`, `task_assignees`, `task_checklist`, `task_links`, `task_progress`, `task_comments`,
  `task_targets`, `target_splits`, `role_templates`, `leave_days`, `points_ledger`, `reward_tiers`, `rag_settings`,
  `reward_months`, `dt_settings` (JSON key/value).
- **Postgres** `tasks` (phase, task_code, title, assignee_id, status, due_date): the old project-plan list. v2 does
  not touch it.
- **Postgres** `seo_backlinks`: the SEO module's backlink **profile** (referring domains from crawlers), shown at
  `/dashboard/seo/backlinks/`. The team's **logged** links live in Backlink Ops (`backlink_ops.db`, `bo_entries`).
  T7 already counts Backlink Ops links as task progress.
- Timestamps are written by the server in UTC ISO. Days, weeks and months are worked out in IST (`now_ist()`).
  v2 keeps that.

### Roles today

- **Superuser** = an email in `DAILY_TRACKER_SUPERUSERS` (default: Jai's two addresses), checked by `taskmgr.is_super`.
  Only the superuser can edit tiers and bonus notes.
- **Admin** = dashboard role `owner` or `admin`. Admins can create and approve tasks, set targets and leave, and review.
- `viewer` is read-only. Everyone else works on their own tasks.
- This already matches the v2 rule (superuser = Jai, admin = everything except role management). Role management
  itself is on `/settings/users/`, which stays as it is.

### What v2 asks for vs what exists

| v2 needs | Exists? | Gap |
|---|---|---|
| Task categories (22, editable) | `work_types` (14, with marks, used by the daily log) | New `task_categories` table. **The 22 names are in the master prompt, which isn't in the repo.** |
| tasks: category, estimate, priority, picked_by, evidence, points_value | T7 `tasks` has title, description, project, priority, due, status, assignees, links | Add columns: category, estimate_min, picked_by/at, pool flag, evidence_url, points_value |
| Task Pool + Pick | No (admins assign) | New: pool tasks with no assignee; Pick = assign to self |
| Quick add in under 1 minute | No. T7 refuses to save without every SMART field | Quick form fills the SMART fields with defaults; full form only behind "Other" |
| `task_events` (immutable) | No (only `task_comments` and status fields) | New table, plus triggers that refuse UPDATE/DELETE |
| Task timer and `work_intervals` | **No time tracking at all** | New. One open interval per user (unique index), start / pause / switch / complete on the server |
| Breaks, lunch, thinking, blocked | No | Interval types. Thinking needs a question and an outcome |
| `time_corrections` | No | New, with approval |
| Leave: emergency (credited 7 h) / planned / holiday | `leave_days(user_id, date, reason)`, set by **any admin**; `*` = company holiday; leave **lowers** the quantity target | Add type, credited_hours, declared_by, declared_at. Emergency = superuser only |
| `work_settings` (7 h, Mon–Sat, Sunday counts, break limits) | Mon–Sat is an env var (`TASK_MANAGER_WORKDAYS`); other settings live in `dt_settings` JSON | New `dt_settings` key `work`, editable in admin. The env var stays the default |
| Hour targets: daily / month-to-date / monthly, Sunday catch-up | Targets are **marks/day** (T4) and **quantity per unit per month** (T7) | New hours engine computed from intervals + leave |
| Signal 🟢 ≥ 95 % / 🟡 80–95 % / 🔴 < 80 % | T7 RAG on quantity: green ≥ 90, amber ≥ 60 | Separate thresholds for hours |
| `points_ledger`, no duplicates | Yes: `UNIQUE(user_id, ref_type, ref_id, reason)` = unique(user, task, rule) | Add `awarded_by` and the v2 rules |
| Badges, levels | `user_badges` (idea winners); Mirror computes badges on read; tiers Bronze to Platinum | New `badges` catalogue, levels Starter → Automation Champion |
| Streaks: Sunday and leave don't break them | T4 streak (marks), T7 "green days", Backlink Ops streak | New hours-based streak |
| Who's on track board, My Day, hourly planner | Mirror and team RAG (quantity) | New screens |
| Reminders | No (T7 left nudges for phase 2) | Step 12 |
| Changelog / SYSTEM_REGISTER / HQ | `CHANGELOG.md` yes. `docs/SYSTEM_REGISTER.md` **isn't in this repo** (it's on an unfound branch), so we write entry files, as before | `docs/SYSTEM_REGISTER_ENTRY_tasks-v2.md` |

### What must not break (checked again after every step)

1. The article pipeline (`/dashboard/seo/articles/…`, publisher, scoring). v2 doesn't touch it.
2. Backlink Ops desk, team scoreboard, per-site levels (`backlink_ops.db`). v2 only reads it.
3. The SEO backlinks profile (`seo_backlinks`, `/dashboard/seo/backlinks/`). Read only.
4. Invoice Desk (`/invoices/`, its own SQLite file).
5. Follow-ups CRM (flag on live), WhatsApp Leads page.
6. **Current `/tasks/`**: every T4 and T7 tab, its API (`/api/tasks/*`, `/api/ideas`), the old task list when the flags
   are off, and the payout sheet.
7. The route registry (`web/lib/routes.json`) and `tests/test_route_registry.py`.
8. Existing tests: `test_task_manager.py` (65), `test_daily_tracker.py`, `test_levels.py`, `test_site_levels.py`,
   `test_followups.py`, `smoke_app.py`, `test_scoring.py`, `test_autoreview.py`, `test_blog_playbook.py`,
   `test_export_html.py`. Two PDF-text checks in `test_invoice_desk.py` already fail on this laptop (reportlab).

### Migration plan

- **Where:** the same `daily_tracker.db`, schema 2 → 3, in `store.init_db()`, the way schema 2 was added:
  `CREATE TABLE IF NOT EXISTS`, plus `ADD COLUMN` that is nullable or has a default. Nothing is dropped or renamed.
  Old code ignores the new tables and columns.
- **Behind a new flag `FEATURE_TASKS_V2`** (default off), switched with `daily-tracker-flags.sh`. Off = exactly
  today's `/tasks/`.
- **Before migrating:** `store.backup("pre-v3")` (already exists) and the deploy script's backup tarball. Rollback = flag
  off (the data stays), or check out the previous commit and restart. The v3 tables are new, so old code never reads
  them.
- **Step 1 tables:** `task_categories`, `task_events` (+ triggers that block UPDATE/DELETE), `work_intervals`
  (+ a partial unique index for one open interval per user), `time_corrections`, `badges`. New columns on `tasks`,
  `leave_days`, `points_ledger`. Work settings go in `dt_settings` key `work`. `user_badges` is reused (new `kind` values).
- **Interval math:** split at IST midnight, so an interval that crosses midnight counts on both days. A user's
  overlapping intervals are merged before summing, so time is never counted twice.

### Questions for Jai (answers change Step 1 onwards)

1. **The master prompt.** Please add `MASTER_DEVELOPMENT_PROMPT.md` to the repo. Step 1 needs its 22 categories,
   Steps 2–13 its 20 acceptance tests, and Step 3 the structured "Other" form and role templates. Without it I'd be
   guessing.
2. **Hours vs output targets.** Today a person's signal comes from **output** (backlinks, blogs per month, T7) and
   **marks** (T4). v2 adds **hours** (7 h/day). My recommendation: the hours signal becomes the headline
   🟢🟡🔴, and the output targets stay in Mirror as a second line. Is that right, or should hours replace them?
3. **Two point systems.** T7 already gives points (task marks × quality × on-time, streak +50, ideas) and tiers use
   them. My recommendation: the v2 rules write into the **same** ledger under their own rule names, so tiers and the
   payout sheet keep working. Do you agree?
4. **Leave.** Today any admin can set leave, and leave lowers the output target. v2: only you declare emergency
   leave, and it credits 7 h. Should the existing admin-set leave become "planned" leave (admins can still set it),
   with emergency leave yours only?
5. **Production flags.** Which flags are on today? Run on the VPS:
   `cat /etc/systemd/system/dashboard-api.service.d/daily-tracker.conf`

### Business continuity

If v2 misbehaves after go-live, `daily-tracker-flags.sh` turns `FEATURE_TASKS_V2` off. `/tasks/` falls back to the
T4/T7 screens and no data is deleted. If the whole dashboard is down, the team logs time in the shared Google Sheet
(the T4 fallback, plus Start and End columns), and an admin imports it afterwards.

## Privacy

Only explicit task events are recorded: no keystrokes, screenshots, browser history, audio or video. The team is
told the rules before go-live.
