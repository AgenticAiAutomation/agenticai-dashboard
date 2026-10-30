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
