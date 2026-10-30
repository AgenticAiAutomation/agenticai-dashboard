# Tasks v3 — "Start my day" flow

Work order: `TASKS_V3_DAY_FLOW_STEPS.md` (Steps 1-10, one at a time). Builds on Tasks v2 (`docs/TASKS_V2.md`),
same branch `feat/tasks-v2`, same database, same guardrails. Flag `FEATURE_TASKS_V3` (needs `FEATURE_TASKS_V2`);
off = the v2 Timer tab exactly as before. Nothing is pushed until Jai says so.

## Decisions (Jai, 27 Oct 2026)

| Topic | Decision |
|---|---|
| Late start | Recorded and shown, **never a penalty** (no points taken, now or in Step 6). |
| Proof | **None in v3.** No 15-minute proof and no proof per chunk: timer time counts toward the day as it runs, and Done needs no link. (Overrides the work order's "one proof per chunk"; `proof_mode` is not built. With v3 off, v2's 15-minute proof is back.) |
| Stopping | Pause just stops, nothing is asked. Only **Dependency** asks why: Credentials expired, Document required or Information required (work setting `block_reasons`), plus who they wait on and an optional detail. |
| After a dependency stop | The screen offers **Jai's daily tasks** first (one tap starts one), then the person's own open tasks, then the Pool. |
| Daily tasks | Jai adds them on the Timer tab (title, category and its fields, priority, everyone or one person) and switches them off or on; never deleted. Jumping to one makes it the person's own task, and jumping again the same day carries on that task instead of making a copy. Table `daily_routines`. |

## Step 1 — Start my day (done 26 Oct 2026, not deployed)

| Rule | How |
|---|---|
| Clock-in | The Timer tab shows only a "Start my day" card (greeting, today's plan) until it's pressed. The server time is saved in `work_days`. Employees (not Jai) land on this tab after login when v3 is on. |
| Late start | After `day_late_after` (work setting, default `10:30` IST) the day is saved as `late`. Shown as a chip. No penalty (points come in Step 6). |
| Tasks | A task starts only inside a started, not-ended day (`day_not_started` / `day_ended`). |
| End my day | Stops the running task (event `auto_pause`, reason "day ended"). Asks to confirm. Pressing again keeps the first time. |
| Forgotten end | Next login, before anything else: "When did you stop?" (time on that day, after the start, not before a timer that ran that day). A timer still running from that day stops at the same time. `end_source = set_later`. The server never guesses. |
| Guardrails | `work_days` rows are never deleted or replaced; a day is ended once; date, start and late/on-time never change. Events `day_start`, `day_end`, `day_end_set` in `task_events`. |

API: `POST /api/tasks/v2/day/start`, `/day/end`, `/day/set-end {end: "YYYY-MM-DDTHH:MM"}`; `GET /v2/state` adds
`dayFlow`, `day`, `openDay`. The table is added to the schema-3 script (`CREATE TABLE IF NOT EXISTS`), so it also
appears on a database that is already at schema 3; no version bump.

Tests: `tests/test_tasks_v3_day.py` (28). v2 timer 48, v2 schema 57, task manager 65, tracker 58, levels 32,
site levels 22, registry 7 pass; `next build` passes. `test_followups` fails on "overdue comes first" on the base
commit too (not this change).

API (27 Oct): `POST /v2/routines` (Jai), `/v2/routines/{id}/active {active}` (Jai), `/v2/routines/{id}/start`;
`/v2/tasks/{id}/block` takes `reason` from `block_reasons` + optional `detail` when v3 is on; state adds `blockReasons`,
`routines`, `routinesAll` (Jai only). Tests now 41.

**Rollback:** `bash /root/daily-tracker-flags.sh nov3`. Data stays.

## Step 2 — daily ring + working hours (done 27 Oct 2026, not deployed)

| Rule | How |
|---|---|
| Ring | Replaces the bar in "Today" when v3 is on. Fills from 0 to today's target with task time only (breaks, lunch and waiting never count). Colour: green ≥ 95 %, amber ≥ 80 % (work setting `signal`). Closed = "🎉 Day complete". Chip: tasks done today. |
| Weekly hours | Jai sets hours per weekday once (default Mon–Sat 7 h, Sunday 0) and it applies to every week: work setting `week_hours`, a new settings row each save (history kept). |
| One day different | Jai sets hours for any date, for everyone, with an optional reason (table `day_hours`, latest row per date wins, rows never changed or deleted). Clear = back to the weekly hours. |
| Target 0 | The ring shows "Off". |

API: `POST /v2/hours/week {week: [Mon..Sun]}` and `/v2/hours/day {date, hours|null, note}` (Jai only, 0–16 h);
state adds `tasksDone`, `hours` (Jai only), `settings.greenMin/amberMin`; `targetMinutes` follows today's hours (v2 too).
Tests now 49.

**Not yet:** confetti and the streak (+1 when the ring closes) come with the streak engine in Step 6; Break and
Lunch chips come with the break buttons in Step 3. Changing the weekly hours also changes past days' targets
(no report reads them yet).

## Step 3 — break buttons (done 30 Oct 2026, not deployed)

| Rule | How |
|---|---|
| Buttons | Break, Lunch, Thinking, Waiting under "Now", once the day has started. One tap: the running task pauses and the break remembers it. The same button (now "Resume") starts that task again. Another button switches, the task carried along. Starting any task, Pause or End my day also ends the break. |
| What counts | Thinking counts toward the ring (as in v2). Break, Lunch and Waiting never do. |
| Limits | From v2 work setting `breaks`: Break 2 × 15 = 30 min, Lunch 1 × 30 = 30 min a day. Chips under the ring show "used X of Y min" and turn amber when over. No pop-up, no block. |

API: `POST /v2/break {type: break|lunch|thinking|waiting}` (v3 only; 409 before Start my day / after End my day);
state adds `breaks: {used: {break, lunch, thinking, waiting}, limit: {break, lunch}}` (minutes, breaks started today).
Tests now 58.

## Flexible hours (30 Oct 2026)

A day can be worked in parts. The ring adds up task time from any part of the IST day. **End my day** can be
undone the same day: the person presses **Resume my day** (Jai can do it for anyone from **Team today**).
`POST /v2/day/reopen {user_id?}` (empty = yourself; someone else = Jai only). Each reopen is a `day_reopen`
event with the earlier end time ("ended 16:00, reopened by the person"). Time between parts never counts.
Work after midnight belongs to the next day. Tests now 67.

## Hour credits, thinking cap, idle debit, Big Ideas (Jai, 30 Oct 2026)

| Rule | How |
|---|---|
| Credits | Work month (26th–25th) so far, finished days only, from the person's first day. All hours count (no daily cap); extra hours make up short days in the same work month. **Owed** = short beyond the allowance, plus idle debit. The person sees "owes 1h 00m / 2h ahead / on track" under the ring. |
| Allowance | Hours someone may be short in a month. Jai sets everyone's (`user_id '*'`) and per person (own row wins) on the Timer tab, card "Hour credits this month". Table `hour_allowance`, append-only, latest wins, default 0. |
| Thinking | Counts as work up to `thinking_cap_minutes` (60) a day; the rest doesn't fill the ring or credits. |
| Idle debit | After a dependency stop or a Waiting tap, if no task or daily task starts within `idle_grace_seconds` (60), the whole gap until the next start (or End my day / midnight) is debited. Overlapping gaps count once. This is on top of the gap not counting as work. |
| Big Ideas | New tab. Open board: everyone sees every idea and searches before submitting. Channel from `idea_channels`. `ideas_required` (1) a month; `ideas_for_nomination` (6) counted in a month = nominee. Jai's statuses: new, assigned (person + project: a task "Apply idea: …" lands on their desk), worked, not_applied, repeat (not counted). Jai picks Employee of the Month from nominees, once a month, final (`employee_of_month`). Table `big_ideas`, rows never deleted; each decision is a task_events row. |

API: `POST /v2/hours/allowance {user_id|'*', hours}`; `GET/POST /v2/ideas`, `POST /v2/ideas/{id}/decide {status, assign_to, project, note}`,
`POST /v2/ideas/employee-of-month {user_id, note}`. State adds `credit`, `teamCredits` + `allowanceAll` (Jai), `settings.thinkingCap`.
Tests: `tests/test_tasks_v3_credits.py` (24).


## Work day, work month, dated hours, Wins (Jai, 30 Oct 2026, later)

| Rule | How |
|---|---|
| Work day | Runs `day_starts_hour` (4 AM) to 4 AM IST, so late-night work stays on the same day. A day nobody ended closes by itself at 4 AM (`end_source 'auto'`, event `day_end_auto`) at the last thing done; a timer left running stops where it started and counts nothing (never guessed). Next day is a normal Start my day. The old "say when you stopped" screen and `/v2/day/set-end` are gone. |
| Work month | 26th to 25th (`month_closes_day`), named by the month it closes in ("2026-11" = 26 Oct–25 Nov). Credits, ideas, Wins and Employee of the Month all use it. Hours after the 25th go to the next work month; a closed one can't be topped up. |
| Weekly hours | Table `week_hours` (week, effective_from), written once. Default start = the next work month (the 26th); Jai may pick a later date or today, never the past. Everyone sees "New working hours from 26 Nov: …" until it starts. Per-date hours also refuse past dates. Past targets never change. |
| No daily cap | The 9-hour cap is gone. |
| Wins (Step 7) | Table `achievements`: what, for whom, result, optional proof link. Jai: Approve / Reject (final, enforced by a trigger) / Ask for more (with a note; the person edits, it goes back). A person sees only their own Wins. |
| Bonus sheet | Jai only, per work month: ideas counted, monthly idea given, ideas worked, Wins approved, rings closed / days with a target, hours owed, nominee, eligible. Eligible = monthly idea given AND at least one worked idea or approved Win; hours and leave never decide it. `GET /v2/bonus.csv?month=`. |

Step 7 overlap: the idea part is Big Ideas (Jai's own rules replace the work order's idea form). Points and badges for
approved items wait for the Step 6 points engine. Tests: credits 41, day 69.

## Step 6 — points and game layer + status ring and month bar (Jai, 30 Oct 2026)

| Rule | How |
|---|---|
| Points | Task = estimate hours × `points_per_hour` (20: 15m = 5, 30m = 10, 1h = 20, 3h = 60) × `complexity_multiplier` (Easy 1, Medium 1.5, Hard 2). Jai's create form has Time (`chunks`) and Complexity (kept in the task's details) and shows the points on offer. Pending until Jai accepts. |
| Accept | Jai's card "Done, waiting for you": Accept (status accepted, `work_points` rule `task`) or Send back with a note (paused). `POST /v2/tasks/{id}/review {accept, note}`. No proof involved (no-proof decision of 27 Oct). |
| Ideas / Wins | Worked Big Idea +`idea_worked_points` (50), approved Win +`win_points` (25), written when Jai decides. |
| Streak | Working days in a row with the day's hours met; days without a target (Sunday, 0-hour dates) don't break it; today counts once met. Leave isn't built yet (Step 9). |
| Levels | v2 `levels` setting, from all points. |
| Badges | Early Bird (on-time start, per day), Ring Closer (hours met, per day), 5-day / 20-day Streak, Hard Mode (5 Hard accepted in an ISO week), Blocker Buster (next task within 2 min of a block), Idea Maker (month's idea given), Achiever (approved Win). Worked out by `game.refresh`, written once. |
| Leaderboard | This week (Monday on): points and days the hours were met, never hours. Everyone sees it on the Timer tab. |
| Ring | No longer fills toward the daily target. Green ("Winning") by default; amber when the month owes hours, red when it owes more than a day's hours. Today's time, streak and points sit beside it. Confetti + chime when the day's hours are met; "Sounds and confetti" switch per browser. |
| Month bar | Hours this work month against the whole month's hours; stops at 99 % until the month's Big Idea is in. |

Tests: `tests/test_tasks_v3_game.py` (22).

## Leave (Jai, 30 Oct 2026)

| Rule | How |
|---|---|
| Allowance | Per work month: `leave_days_per_month` (2) full days + `short_leaves_per_month` (2) short leaves of up to `short_leave_hours` (2.5). Jai sets everyone (`'*'`) or any person differently (table `leave_policy`, latest row wins, own row beats `'*'`) on the Timer tab, card "Leave allowances". |
| Taking it | The person, on the Timer tab: Full day or Short leave, today or later, one leave a day, inside the allowance. Rows in v2 `leave_calendar` (type `full` / `short`, `credited_hours` = hours excused). Cancel your own until the day passes; Jai cancels anyone's. |
| Effect | `user_target` = the day's hours less that person's leave. Credits, the month bar, streaks (a full leave day doesn't break it) and the leaderboard use it. |
| Carry forward | Unused leave of a work month moves to the next one only, as hours: unused days × `daily_target_hours` (7) + unused short leaves × their hours, added to that month's balance (`carriedMinutes`). Nothing carries for someone who hadn't started yet. |

API: `POST /v2/leave {type, date, hours?, reason?}`, `/v2/leave/{id}/cancel`, `/v2/leave/policy {user_id|'*', days, short_count, short_hours}`.
Tests: `tests/test_tasks_v3_leave.py` (28).

## Q&A (Jai, 30 Oct 2026)

Jai asks one person about their work (in general or one of their tasks). Only Jai (superusers) and that person
see the thread. Open = waiting for the person: a red block on top of their Tasks page (and dashboard).
Answered = waiting for Jai: a red block on top of his dashboard and Tasks page, where he asks more (back to open)
or presses **Done ✓**. Done threads go to **Q&A history**: searchable by words or task, by person for Jai, for the
last 12 months; Jai can reopen one. Tables `questions` (never deleted; who/what/when never change) and
`question_messages` (written once). The bar refreshes every minute.
API: `GET /v2/questions`, `GET /v2/questions/history?q=&who=`, `POST /v2/questions {to_user, task_id?, question}`,
`/v2/questions/{id}/reply {body}`, `/done`, `/reopen`. Tests: `tests/test_tasks_v3_qa.py` (23).

## Owner tag (Jai, 30 Oct 2026)

Employees never see the owner's name. Every screen says "Owner" / "the owner" instead of "Jai"; the API masks
superusers' names as "Owner" for anyone who isn't a superuser (`worktime.names_for`): Q&A messages, ideas the
owner gives, the people list (and a "waiting on" the owner is saved as "Owner"). Jai still sees real names.
