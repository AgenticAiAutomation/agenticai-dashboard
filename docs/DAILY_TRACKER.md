# Daily Tracker, per-site levels, /articles removal — work order of 13 Oct 2026

Branch `feat/daily-tracker-levels` (cut from `feat/blog-playbook` @ f06a7d9). Spec:
`DASHBOARD_FIX_AND_TRACKER_SPEC_13Oct.md`. Team guide: `docs/DAILY_TRACKER_GUIDE.md`.

## T1 — Akash could not see whatsappautomation.co.in

Root cause, found in the code. The live data could not be read from here, so this is
the code path, not a database row.

1. The site shipped **inactive** (`active: False` in `backlink_ops/seed.py`, from when the
   domain was parked). The desk hid inactive sites from every non-superuser, and on load
   moved them to the first live site. That happened **even when they were rostered on it**.
2. The desk tied a roster row to a login by comparing **display names exactly, case
   included**, in the browser. "Akash" on the roster never matched the login "Akash Yadav".
3. There is no other assignment. The roster (Backlink Ops → Difficulty & team) is the only
   place a person is put on a site. The dashboard's `assigned_verticals` is a different
   thing (SEO verticals).

Fixed for **all** users, not just Akash (`backlink_ops/assignments.py`):

- A roster row has an optional **login email**. It matches by email, then by full name,
  ignoring case and spaces. One person can have several rows, one per site.
- A site that is not live is still shown to everyone rostered on it.
- `whatsappauto` now ships active, because the domain answers 200. The desk can still hide it.
- The superuser's grid lists **roster rows that match no login**. That makes this failure
  visible the next time it happens.

**What Jai does after deploy:** on the desk, open Difficulty & team. Put
`akash0710yadav@gmail.com` in Akash's row, set the site to WA Auto, and click Save team.
Akash reloads the page (no new login needed: the projects are read on every load, not
from the token). His dashboard role must be `seo_lead`, `seo`, `admin` or `owner`. A
`writer` or `viewer` sees the desk read-only.

## T2 — one level per (person, website). Flag `FEATURE_PER_PROJECT_LEVELS`

- New table `bo_user_levels` in `backlink_ops.db` (schema 1 → 2, additive). It holds
  user_id (dashboard id), project_id, level, xp, current_difficulty, streak_days and
  last_completed_date, UNIQUE(user_id, project_id).
- **Migration:** at upgrade, the global level is recorded (`levels_v2_migration`). A pair
  is created the first time that person opens that site, at the global level, so nobody
  drops to L1. With the flag on, the old "Difficulty level" control becomes
  "Starting level".
- The Today score card is now **your own links at your own level**. The sheet, review
  queue and All-projects tab are still site-wide. Each link is still scored against the
  whole site's sheet, so per-person points add up to the site total.
- XP is lifetime points on that site. The streak counts consecutive days with every
  requirement met; today in progress never breaks it. These are recomputed from the links
  on read.
- The level changes only when Jai changes it (Difficulty & team → Levels by person and
  site). That keeps the existing rule. A pair with a 5-day streak shows **ready**.
  Difficulty still ramps with the level (L1 Warm-up → L5 Elite targets, unchanged).
- Scoreboard and All-projects judge each pair at its own level.
- API (superuser-only where noted): `GET /api/seo/backlink-ops/levels` (mine),
  `GET …/levels/all` (grid, superuser), `PUT …/levels` `{userId, project, level}` (superuser).
  The flag off makes all three answer 404, and the desk behaves exactly as v1.2.
- Homepage: a **Workspace** row (Backlink Ops, Daily Tracker, Invoices for admins) and
  **My levels** (site · level · today's bar · streak). The superuser sees the
  everyone × every-site grid.

## T3 — /articles/ removed

- The page is archived at `archive/removed_2026-10-13/` (restore steps are in its README).
  `/articles/` now redirects to `/`, and the Articles nav link is gone.
- Kept: the `/articles` API (still read by `/countries/`) and **all of blog publishing**
  (`/api/seo/articles` + `seo/services/publisher.py` → `published/articles`). The removed
  page never touched either.

## T4 — Daily Tracker + Idea Board. Flags `FEATURE_DAILY_TRACKER`, `FEATURE_IDEA_BOARD`

Module `api/app/daily_tracker/`, with its own SQLite file `instance/daily_tracker.db`
(same pattern as Invoice Desk). The spec's tables are `work_types`, `daily_logs`,
`user_targets`, `ideas` and `idea_votes`. There are two more: `user_badges` (the
"bonus flag", no amounts) and `dt_people` (who has opened the tracker, for leaderboards).

| Rule | How |
|---|---|
| Sites | Only the sites you are rostered on in Backlink Ops (same check as T1). Admins see all. |
| Proof | URL required, http(s). Note ≤ 300 chars, required for "Other". Minutes 0–1440. |
| Date | Today by default. Up to 7 days back. Future dates refused. |
| Late | Date before the day it was submitted → **50%**. A fix after "needs fix" keeps the original verdict. |
| Marks | base marks (copied at submit) × quality (1→0, 2→0.5, 3→1, 4→1.25, 5→1.5) × late factor. Only **approved** counts. |
| Duplicates | Same link (scheme, www, case, trailing /, #, utm_* ignored) refused if already logged and not rejected, or if it is in Backlink Ops. |
| Backlink Ops | Shown automatically, one row per person, site and day. Each link approved there earns "Backlink built" marks (5), **capped at 20/day** (setting). Never re-entered, never double-counted. |
| Target | Default 40/day; per person with an effective date. Hit → confetti (once a day) and streak. |
| Ideas | New → Shortlisted → In trial → Worked ✅ / Didn't work. "Worked" needs a result note and gives the author that month's winner badge. 👍 toggles; you can't vote for your own idea. |
| Admin | Review queue (single and bulk), report with % of days on target, CSV export, import from the backup sheet, work types and marks, targets, cap. |

API: `GET /api/tasks/status`, `GET|PUT /api/tasks/work-types`,
`POST|GET /api/tasks/logs`, `PUT|DELETE /api/tasks/logs/{id}`,
`POST /api/tasks/logs/{id}/review`, `POST /api/tasks/logs/review-bulk`,
`GET /api/tasks/review-queue`, `GET /api/tasks/summary?range=day|week|month`,
`GET /api/tasks/report`, `GET /api/tasks/export.csv`, `POST /api/tasks/import`,
`PUT /api/tasks/settings`, `PUT /api/tasks/targets`, `GET|POST /api/ideas`,
`POST /api/ideas/{id}/status`, `POST /api/ideas/{id}/vote`. They are JWT-protected through
the same hook as Invoice Desk. Admin = role owner/admin or a superuser email.

With both flags off, nothing is mounted and `/tasks/` shows the old task list unchanged.

## Deploy, flags, rollback

1. `ops/deploy-daily-tracker.sh --yes` (copy to `/root/daily-tracker-deploy.sh`). It takes
   backups (pg_dump, code tarball, all three desk SQLite files, frontend build), checks
   out the new code, restarts, checks (Backlink Ops 1.3.0 / schema 2, routes) and rebuilds
   the frontend. If anything fails before the frontend, it rolls back by itself. All flags
   stay off.
2. `ops/daily-tracker-flags.sh levels`, then `tracker`, then `ideas`. Each writes the
   drop-in `dashboard-api.service.d/daily-tracker.conf` and restarts.
3. Rollback: `daily-tracker-flags.sh off` hides everything and deletes no data. To undo the
   code too: `git checkout <hash in /root/backups/daily-tracker-*/previous-commit.txt>` and
   restart. Old code ignores `bo_user_levels` and `daily_tracker.db`.

Continuity: if the dashboard is down, the team logs in the shared Google Sheet (Email,
Project, Work type, Link, Note, Minutes, Date). An admin imports it afterwards from Report
& settings.

## Tests

`PYTHONPATH="api;." python tests/test_levels.py` (32 checks: T1 + T2),
`python tests/test_daily_tracker.py` (58: the spec §5 list for T4). The existing
`smoke_app.py` (61), `test_autoreview`/`test_scoring` (23) and `test_blog_playbook`/`test_export_html` (43)
pass unchanged. In `test_invoice_desk.py`, 2 PDF-text checks fail on this laptop
**on the base commit too** (reportlab version). This change does not cause them.

## Decisions taken on Jai's open questions (§9). Change any of them in settings.

1. Akash's role: unchanged by code. He needs `seo_lead` (or `seo`) to log, so check it on the Users page.
2. Daily target: 40 marks, editable per person.
3. Base marks: the spec's examples. Blog written 10, Keyword research / Competitor analysis /
   Image / Technical fix 5, GBP 3, Forum 3, Directory 2.
4. Bonus: **every** idea marked Worked gets the badge. There can be several winners in a month.
5. "Embedded in homepage and Invoices": read as Workspace cards + My levels on the
   homepage, and Invoices in the nav for admins (as the spec assumed).

Two of my own choices also need Jai's OK. First, Backlink Ops links count 5 marks each, up to
20 a day, in the tracker. Second, the per-site level does not rise from tracker marks, only
from Backlink Ops days, and only when Jai raises it.
