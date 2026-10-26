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

### Migration plan (revised after Jai's decisions)

- **Where:** the same `daily_tracker.db`, schema 2 → 3, in `store.init_db()` → `_migrate_v3()`.
  **Only new tables.** No existing table gets even a new column (Jai: "the database remains the same, with a
  new task table").
- **Never delete or replace:** SQLite triggers on every v2 table refuse DELETE. `recursive_triggers` is on, so
  INSERT OR REPLACE is refused too. The event trail, 15-minute proof, points, settings history, awards and employee
  of the month can never be edited. An interval can only be closed, once. Leave can only be cancelled, once. A time
  correction is decided once.
- **Behind a new flag `FEATURE_TASKS_V2`** (default off), added in Step 2 when there are screens to switch.
- **Backup:** `_migrate_v3` writes `backups/daily_tracker/daily_tracker-<time>-pre-v3.db` before it creates anything.
- **Interval math:** split at IST midnight. A user's overlapping intervals are merged before summing, so time is
  never counted twice.

### Decisions (Jai, 26 Oct 2026)

| Topic | Decision |
|---|---|
| Past days | Locked at IST midnight. The employee can't edit yesterday. A fix goes as a correction request (reason + proof) that only Jai approves; the original stays saved next to it. |
| Database | Existing tables stay exactly as they are. v2 gets new tables, and its data is never deleted or replaced. |
| 15-minute proof | The employee starts a task timer. Every 15 minutes they record what they did: link/URL, domain, URL slug, image name, logo name, note. A 15-minute block with no proof doesn't count as worked time. |
| Leave | Sunday is off. Each employee can mark **2 leave days a month** themselves. Those days, and any leave Jai creates (emergency, planned, holiday), never hurt daily, weekly or monthly progress. A third self-marked day counts as a normal missed day. |
| Superuser view | Jai sees everyone's progress, plus an effort graph like Google Search Console's: last 24 h, 3, 7, 15, 30, 60 and 90 days. **Employee of the month** is always shown. |
| Employee view | "How much is left": today's hours left, and the hours a day needed to finish the month. |
| Headline signal | Hours (7 h/day). The T7 output targets stay in Mirror as a second line. |
| Points | A separate v2 ledger (`work_points`), because existing tables don't change. Tiers are linked up in Step 9. |
| Master prompt | Not available. Go ahead without it: 22 editable categories (the 13 T4 work types + Design, Development, Automation, Research, SOP, Office, Meeting, Learning, Other), and tests written from this work order. |

Still open: which flags are on in production (`cat /etc/systemd/system/dashboard-api.service.d/daily-tracker.conf`).

## Step 1 — database foundation (done 26 Oct 2026, not deployed)

| Spec table | Built as | Notes |
|---|---|---|
| task_categories | `task_categories` | 22 seeded, editable, no delete |
| tasks (extend) | **`work_tasks`** (new) | category, project/site, domain, priority, estimate_min, status, pool, assigned_to, picked_by/at, due_date, evidence_url, points_value. Status may change; creator and created time may not |
| task_events | `task_events` | write-once |
| work_intervals | `work_intervals` | type work / break / lunch / blocked / thinking; question/outcome for thinking; **one open interval per person** (unique index); closed once |
| (15-min proof) | `work_slots` | url, domain, url_slug, image_name, logo_name, note; one row per person per slot; write-once |
| time_corrections | `time_corrections` | original + new value, reason, evidence; pending → approved/rejected once |
| leave_days | **`leave_calendar`** (new) | type allowance / emergency / planned / holiday (`*`), credited_hours, declared_by/at; cancel once, row stays |
| work_settings | `work_settings` | append-only JSON history, latest row wins: 7 h, Mon–Sat, Sunday counts, 15-min slots, 2 leaves/month, past-day lock, breaks, signal 95/80, points, levels, leaderboard visibility |
| points_ledger | **`work_points`** (new) | UNIQUE(user, rule, ref): one award per rule per task/day/month; write-once |
| badges, user_badges | `badges`, **`badges_awarded`** | 7 badges seeded |
| (employee of the month) | `employee_of_month` | one per month, write-once |

Tests: `PYTHONPATH="api;." python tests/test_tasks_v2_schema.py` (47 checks). They build a real schema-2 database with
the existing code and add T4/T7 rows, then upgrade it. They check the backup, that every old table and row is
byte-for-byte unchanged, that a second run changes nothing, every guardrail, and the rollback. The existing suites
still pass: task manager 65, tracker 58, levels 32, site levels 22, follow-ups 38, registry 7. `smoke_app` stops at
check 52 because Flask isn't installed on this laptop, and it does the same on the base commit.

**Rollback (Step 1):** stop the API, copy `backups/daily_tracker/daily_tracker-*-pre-v3.db` over
`instance/daily_tracker.db` (delete its `-wal` and `-shm` files first), check out the previous commit, and start it
again. Or simply leave the tables: old code never reads them.

## Business continuity

If v2 misbehaves after go-live, `daily-tracker-flags.sh` turns `FEATURE_TASKS_V2` off. `/tasks/` falls back to the
T4/T7 screens and no data is deleted. If the whole dashboard is down, the team logs time in the shared Google Sheet
(the T4 fallback, plus Start and End columns), and an admin imports it afterwards.

## Privacy

Only explicit task events are recorded: no keystrokes, screenshots, browser history, audio or video. The team is
told the rules before go-live.
