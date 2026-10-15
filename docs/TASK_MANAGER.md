# Route registry (T5) and task manager (T7), 15 Oct 2026 work order

Branch `feat/task-manager` (cut from `feat/daily-tracker-levels`, which is live). Spec:
`DASHBOARD_FIX_AND_TRACKER_SPEC (2).md`. T1–T4 are in `docs/DAILY_TRACKER.md`; T6 (Blog Gate) is not built yet.

## T5: route registry

- `web/lib/routes.json` is **the** list of pages. Each entry has slug, title, icon, roles, group (SEO · Content · Team ·
  Finance · Admin), status (live / hidden / planned / removed) and a one-line purpose.
- The top nav (`nav`), the SEO sub-tabs (`tab`) and the homepage Workspace grid all read it.
- The homepage shows every **live** page this role may open. Each card has its full URL and a Copy button. Pages tied
  to a flag (`requires`) appear only when that flag is on.
- Removed (`/articles/`), planned (`/blog-gate/`) and deep pages (`/write`, `/edit`) never show.
- **Add a page:** add one entry. `tests/test_route_registry.py` fails if a `web/app/**/page.tsx` is not in the registry,
  or if a slug doesn't resolve. The deploy script also opens every live slug from outside.

## T7: task manager (`FEATURE_TASK_MANAGER`)

| Part | How it works |
|---|---|
| SMART | The API refuses to save unless every field is filled: title + deliverable (S); number, unit and proof type (M); effort hours (A); website + goal (R); start + due (T); plus assignee(s) and priority. Over 40 h of open work in the week → a warning, not a block. Recurrence: daily / weekly / monthly. A missed period skips ahead and gets one new copy, not a pile. |
| Status | To do → In progress → Submitted → Approved / Needs fix, plus Blocked (with a reason). Assignees move their own tasks; admins approve. "Needs fix" counts as rework. |
| Views | My tasks: list, board (kanban), calendar. Admins: an All-team table filtered by person, site, status and due date. |
| Auto progress | Tasks counting `backlinks`, `blogs`, a Daily Tracker work type, or ideas update themselves. Backlink Ops links (not rejected) on that site; articles assigned to the person and published; **approved** daily logs of that type; ideas. Each source row counts once. A rejected link stops counting. Any other unit is counted by hand: quantity + proof link, and the same link can't count twice. |
| Approval | points = task marks × quality (1→0 … 5→1.5) × 1.10 if submitted on time. Every assignee gets them in the ledger **and** as XP on their per-site level (T2). |
| Targets | Monthly target per person per site per unit. It is split evenly over working days (Mon–Sat; `TASK_MANAGER_WORKDAYS`), and Jai can edit any week. A leave day or company holiday (`*`) is 0; it lowers the target, it isn't pushed onto other days. Role templates (per week) give a new person targets in one click. |
| RAG | Task: % of expected progress by now (green ≥ 90, amber ≥ 60, red below; overdue = red; due in < 24 h and not submitted = amber). Person: the same, against their planned targets for today / this week / this month. Today counts by the share of the working day gone (9:00–19:00 IST). Any overdue task makes that period red. Thresholds are editable. |
| Mirror | The 3 signals, a 30-day signal strip, on-time %, quality average, rework, points this month, tier and gap to the next, concrete "scope to earn more", rank (Jai can hide it from people), best and weakest work types, and badges. |
| Weekly idea | Every associate gets a task each week: one idea, due Friday 18:00. Submitting an idea (problem, idea, 2-week test, metric, effort) completes it. If none by Friday, it's red. |
| Points | Approved daily-log marks; task points; streak bonus +50 for each 7 green days in a row; ideas +5 submitted, +20 trialled, +100 worked. Tiers default to Bronze 300 / Silver 600 / Gold 1000 / Platinum 1500; **only Jai** edits them and their bonus note. A person sees only their own tier's bonus; admins see all. Monthly sheet → Jai approves → CSV for payout (paid offline). |
| Badges | Streak 7 / 30, Zero overdue month, Top quality (avg ≥ 4.5 over 5+ reviewed), Idea of the Month. |

### Decisions taken (change them in settings, or tell me)

- Working days are Monday to Saturday. Set `TASK_MANAGER_WORKDAYS=0,1,2,3,4` for Monday to Friday.
- A "green day" for the streak bonus means the person's targets were met. On a day with no target, it means the Daily
  Tracker marks target was hit.
- Blog progress counts **published** articles. When T6 lands, it will count only articles that passed the gate.
- The spec's `user_targets(...)` table is named `task_targets`, because T4 already uses `user_targets`.
- Admins don't get weekly-idea tasks or appear in the team grid or rewards; Jai's own work isn't scored.
- WhatsApp/email nudges are phase 2 (spec), not built.

## Switch on and roll back

1. `bash /root/task-manager-deploy.sh --yes` takes backups, deploys and checks every registry page from outside. The
   flags stay as they are.
2. `bash /root/daily-tracker-flags.sh tasks` turns the task manager on. The Daily Tracker and Idea Board flags work
   with it but aren't required.
3. Rollback: `daily-tracker-flags.sh off` (data kept), or check out the commit in
   `/root/backups/task-manager-*/previous-commit.txt` and restart. Old code ignores the new tables.

## Tests

`tests/test_task_manager.py` runs 65 checks: the spec's §7.10 list plus permissions, recurrence and the payout sheet.
`tests/test_route_registry.py` runs 7.
