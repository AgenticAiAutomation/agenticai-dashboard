# Follow-ups (CRM): who to call, when, about what

Flag `FEATURE_FOLLOWUPS` (switch on: `bash /root/daily-tracker-flags.sh crm`). Module `api/app/followups/`, own SQLite
`api/instance/followups.db`. Owner/admin logins and the superuser emails only.

| Where | What |
|---|---|
| Homepage | The "Follow-ups" card: **To do** (overdue first, then today by priority P1→P3), **Upcoming** (14 days), **Done** (latest 20). Each line has the phone (tap to call), WhatsApp, email, and what happened last time. |
| `/followups/` | The same board, a month calendar, and contacts. Click a contact for their details (editable), notes and full history. |
| Done | You must write what happened: that is the log the next call starts from. Tick "Book the next follow-up" to schedule the next step in the same go. "+1 day" moves it to tomorrow. |

First start loads the four follow-ups Jai listed on 22 Oct 2026 (Kaushik payment Mon 26, Vinod Aggarwal meeting Mon
26, Aman / Hospital Cloud.ai Tue 27, Genpact call Sat 24 at 3 pm about McDonald's). Phones are blank: add them. They
load only into an empty database, once; `FOLLOWUPS_SEED=0` skips them.

API: `/api/followups/status`, `/board`, `/calendar`, `/items` (+ `/{id}`, `/{id}/done`, `/{id}/snooze`),
`/contacts` (+ `/{id}`, `/{id}/notes`). Tests: `tests/test_followups.py` (25). Rollback: flag off (data kept).
