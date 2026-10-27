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
