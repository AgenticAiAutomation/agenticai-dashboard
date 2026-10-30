"""Daily Tracker — storage.

A SEPARATE SQLite file, like Backlink Ops and Invoice Desk: nothing here can
lock, migrate or corrupt the dashboard's Postgres, and rollback is one
un-registered router. Every table is new (the spec's names); nothing that
exists today is altered.

user_id is the dashboard users.id. Name and email are copied onto each row so
reports and the CSV read without a join into the host database.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .config import settings

IST = timezone(timedelta(hours=5, minutes=30))
_local = threading.local()

# Spec §4A list, with the example marks from §4B. Admin-editable afterwards.
# kind: 'backlink' = the type Backlink Ops rows show as; 'other' = note required.
DEFAULT_WORK_TYPES = [
    ("Blog article written", 10, ""),
    ("Blog article published", 20, ""),
    ("Backlink built", 5, "backlink"),
    ("Guest post", 15, ""),
    ("Social media post", 2, ""),
    ("Forum / Q&A answer (Quora, Reddit)", 3, ""),
    ("Directory / citation listing", 2, ""),
    ("On-page fix (title, meta, schema, speed)", 5, ""),
    ("Keyword research done", 5, ""),
    ("Competitor analysis", 5, ""),
    ("Image / video / infographic created", 5, ""),
    ("Google Business Profile update", 3, ""),
    ("Technical SEO fix", 5, ""),
    ("Other (must describe)", 3, "other"),
]

DEFAULT_SETTINGS = {
    "default_daily_target": 40,
    # Backlink Ops links already earn points on that desk. Here each APPROVED
    # link shows as "Backlink built" and earns that type's marks, capped per
    # day so 40 links do not swamp the tracker. 0 = show them, count nothing.
    "backlink_daily_cap": 20,
    "late_factor": 0.5,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS dt_schema_version (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS dt_settings (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_by TEXT, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS work_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    base_marks  REAL NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    kind        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    user_name     TEXT NOT NULL DEFAULT '',
    user_email    TEXT NOT NULL DEFAULT '',
    project_id    TEXT NOT NULL,
    work_type_id  INTEGER NOT NULL REFERENCES work_types(id),
    base_marks    REAL NOT NULL DEFAULT 0,
    proof_url     TEXT NOT NULL,
    proof_key     TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 0,
    log_date      TEXT NOT NULL,
    submitted_at  TEXT NOT NULL,
    late          INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'submitted',
    quality       INTEGER,
    marks_awarded REAL NOT NULL DEFAULT 0,
    reviewer_id   TEXT,
    reviewer_name TEXT,
    reviewed_at   TEXT,
    review_note   TEXT,
    source        TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS ix_dl_user_date ON daily_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS ix_dl_status ON daily_logs(status);
CREATE INDEX IF NOT EXISTS ix_dl_proof ON daily_logs(proof_key);

CREATE TABLE IF NOT EXISTS user_targets (
    user_id            TEXT NOT NULL,
    daily_marks_target REAL NOT NULL,
    effective_from     TEXT NOT NULL,
    set_by             TEXT,
    PRIMARY KEY (user_id, effective_from)
);

CREATE TABLE IF NOT EXISTS ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    user_name       TEXT NOT NULL DEFAULT '',
    project_id      TEXT NOT NULL,
    title           TEXT NOT NULL,
    problem         TEXT NOT NULL DEFAULT '',
    idea            TEXT NOT NULL DEFAULT '',
    expected_result TEXT NOT NULL DEFAULT '',
    metric          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'new',
    result_note     TEXT NOT NULL DEFAULT '',
    month_won       TEXT,
    decided_by      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idea_votes (
    idea_id   INTEGER NOT NULL REFERENCES ideas(id),
    user_id   TEXT NOT NULL,
    voted_at  TEXT NOT NULL,
    UNIQUE (idea_id, user_id)
);

-- Everyone who has opened the tracker: the leaderboard and the admin report
-- list people from here (the host users table is not read).
CREATE TABLE IF NOT EXISTS dt_people (
    user_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    role       TEXT NOT NULL DEFAULT '',
    last_seen  TEXT NOT NULL
);

-- The "bonus flag on the user record", kept here so the host users table is
-- untouched. No amounts: pay is handled offline.
CREATE TABLE IF NOT EXISTS user_badges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    user_name  TEXT NOT NULL DEFAULT '',
    month      TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'idea_winner',
    idea_id    INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, month, kind, idea_id)
);
"""


# ------------------------------------------------------------------------
# Schema 2 (T7, task manager). All additive: new tables, and new nullable
# columns on ideas / daily_logs. Nothing existing is renamed or dropped.
# The spec's `user_targets(user_id, project_id, period, work_type, qty, month)`
# would collide with T4's user_targets (daily marks target), so it is
# `task_targets`. Bonus notes live on reward_tiers, never amounts on people.
SCHEMA_2 = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    project_id    TEXT NOT NULL,
    goal          TEXT NOT NULL,
    target_qty    REAL NOT NULL,
    unit          TEXT NOT NULL,
    work_type_id  INTEGER,
    proof_type    TEXT NOT NULL DEFAULT 'link',
    effort_hours  REAL NOT NULL,
    priority      TEXT NOT NULL DEFAULT 'P2',
    start_at      TEXT NOT NULL,
    due_at        TEXT NOT NULL,
    recurrence    TEXT NOT NULL DEFAULT 'none',
    series_id     INTEGER,
    status        TEXT NOT NULL DEFAULT 'todo',
    blocked_reason TEXT NOT NULL DEFAULT '',
    marks         REAL NOT NULL DEFAULT 0,
    quality       INTEGER,
    rework        INTEGER NOT NULL DEFAULT 0,
    kind          TEXT NOT NULL DEFAULT 'task',
    week          TEXT,
    submitted_at  TEXT,
    approved_at   TEXT,
    approved_by   TEXT,
    review_note   TEXT NOT NULL DEFAULT '',
    created_by    TEXT NOT NULL,
    created_by_name TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_series_start ON tasks(series_id, start_at) WHERE series_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_weekly_idea ON tasks(kind, week, created_by) WHERE kind = 'weekly_idea';

CREATE TABLE IF NOT EXISTS task_assignees (
    task_id   INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id   TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    UNIQUE (task_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_ta_user ON task_assignees(user_id);

CREATE TABLE IF NOT EXISTS task_checklist (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    done    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_links (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    url     TEXT NOT NULL,
    label   TEXT NOT NULL DEFAULT ''
);

-- One row per counted unit of work. Synced rows (backlink / blog / daily_log /
-- idea) are rebuilt from their source on every sync, keyed by source_id, so a
-- link can never count twice and a rejected one stops counting.
CREATE TABLE IF NOT EXISTS task_progress (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,
    qty        REAL NOT NULL DEFAULT 1,
    source     TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    proof_url  TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (task_id, source, source_id)
);

CREATE TABLE IF NOT EXISTS task_comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,
    user_name  TEXT NOT NULL DEFAULT '',
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_targets (
    user_id    TEXT NOT NULL,
    project_id TEXT NOT NULL,
    unit       TEXT NOT NULL,
    month      TEXT NOT NULL,
    qty        REAL NOT NULL,
    set_by     TEXT,
    PRIMARY KEY (user_id, project_id, unit, month)
);
-- Jai's edits to the automatic weekly split. week_start = that week's Monday.
CREATE TABLE IF NOT EXISTS target_splits (
    user_id    TEXT NOT NULL,
    project_id TEXT NOT NULL,
    unit       TEXT NOT NULL,
    month      TEXT NOT NULL,
    week_start TEXT NOT NULL,
    qty        REAL NOT NULL,
    PRIMARY KEY (user_id, project_id, unit, month, week_start)
);
CREATE TABLE IF NOT EXISTS role_templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    role         TEXT NOT NULL,
    unit         TEXT NOT NULL,
    qty_per_week REAL NOT NULL,
    UNIQUE (role, unit)
);
CREATE TABLE IF NOT EXISTS leave_days (
    user_id TEXT NOT NULL,
    date    TEXT NOT NULL,
    reason  TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS points_ledger (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    user_name  TEXT NOT NULL DEFAULT '',
    points     REAL NOT NULL,
    reason     TEXT NOT NULL,
    ref_type   TEXT NOT NULL,
    ref_id     TEXT NOT NULL,
    month      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, ref_type, ref_id, reason)
);
CREATE INDEX IF NOT EXISTS ix_pl_month ON points_ledger(month, user_id);

CREATE TABLE IF NOT EXISTS reward_tiers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    min_points REAL NOT NULL,
    bonus_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rag_settings (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    green_min REAL NOT NULL DEFAULT 90,
    amber_min REAL NOT NULL DEFAULT 60
);
-- Monthly payout sheet once Jai approves it (tier per person; no amounts).
CREATE TABLE IF NOT EXISTS reward_months (
    month       TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    user_name   TEXT NOT NULL DEFAULT '',
    points      REAL NOT NULL,
    tier        TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    PRIMARY KEY (month, user_id)
);
"""

# Columns added to existing tables (schema 2). Each is nullable or defaulted.
ADD_COLUMNS = [
    ("ideas", "week", "TEXT"),
    ("ideas", "test_plan", "TEXT NOT NULL DEFAULT ''"),
    ("ideas", "effort", "TEXT NOT NULL DEFAULT ''"),
    ("daily_logs", "rework", "INTEGER NOT NULL DEFAULT 0"),
]

# ------------------------------------------------------------------------
# Schema 3 (Tasks v2: timer, 15-minute proof, hours targets). Jai's rule: the
# existing tables stay exactly as they are, v2 gets NEW tables only, and its
# data is never deleted or replaced. The triggers below enforce that in the
# database itself, so no code path (or a hand-typed sqlite3 command) can do it.
# Names that would collide with T4/T7 tables get a new name:
#   spec tasks -> work_tasks, leave_days -> leave_calendar,
#   points_ledger -> work_points, work_settings is append-only (latest row wins).
V3_TABLES = ["task_categories", "work_tasks", "task_events", "work_intervals", "work_slots", "task_holds",
             "time_corrections", "leave_calendar", "work_settings", "work_points", "badges",
             "badges_awarded", "employee_of_month", "work_days", "daily_routines", "day_hours", "hour_allowance",
             "big_ideas"]

SCHEMA_3 = """
CREATE TABLE IF NOT EXISTS task_categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    role       TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    -- JSON list of what the person MUST fill in: [{"key","label","type":"text|choice","options":[..]}]
    fields     TEXT NOT NULL DEFAULT '[]',
    -- >0: due this many working days after the task is picked (approved holds add back)
    deadline_workdays INTEGER NOT NULL DEFAULT 0,
    -- 1: stopping the watch for a dependency waits for Jai's approval
    hold_needs_approval INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- pool = 1 while nobody has picked it. Status is free text checked by the app
-- (a CHECK would need a table rebuild to extend, and rebuilds are not allowed).
CREATE TABLE IF NOT EXISTS work_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    category_id   INTEGER REFERENCES task_categories(id),
    project_id    TEXT NOT NULL DEFAULT '',
    domain        TEXT NOT NULL DEFAULT '',
    priority      TEXT NOT NULL DEFAULT 'P2',
    estimate_min  INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pool',
    pool          INTEGER NOT NULL DEFAULT 0,
    assigned_to   TEXT,
    picked_by     TEXT,
    picked_at     TEXT,
    due_date      TEXT,
    evidence_url  TEXT NOT NULL DEFAULT '',
    details       TEXT NOT NULL DEFAULT '{}',   -- the category's required fields, filled in
    points_value  REAL NOT NULL DEFAULT 0,
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_wt_assigned ON work_tasks(assigned_to, status);
CREATE INDEX IF NOT EXISTS ix_wt_pool ON work_tasks(pool, status);

CREATE TABLE IF NOT EXISTS task_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    task_id    INTEGER,
    event_type TEXT NOT NULL,
    server_ts  TEXT NOT NULL,
    prev_state TEXT NOT NULL DEFAULT '',
    new_state  TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT 'web',
    actor_id   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_te_user ON task_events(user_id, server_ts);
CREATE INDEX IF NOT EXISTS ix_te_task ON task_events(task_id);

-- type: work | break | lunch | blocked | thinking. Thinking needs question at
-- start, outcome at end (app). One OPEN interval per person, enforced here.
CREATE TABLE IF NOT EXISTS work_intervals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    task_id    INTEGER,
    type       TEXT NOT NULL DEFAULT 'work',
    start_ts   TEXT NOT NULL,
    end_ts     TEXT,
    is_manual  INTEGER NOT NULL DEFAULT 0,
    question   TEXT NOT NULL DEFAULT '',
    outcome    TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wi_one_open ON work_intervals(user_id) WHERE end_ts IS NULL;
CREATE INDEX IF NOT EXISTS ix_wi_user_start ON work_intervals(user_id, start_ts);

-- The 15-minute proof: what was done in that slot, with evidence.
CREATE TABLE IF NOT EXISTS work_slots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT NOT NULL,
    task_id      INTEGER,
    interval_id  INTEGER,
    slot_start   TEXT NOT NULL,
    slot_minutes INTEGER NOT NULL DEFAULT 15,
    url          TEXT NOT NULL DEFAULT '',
    domain       TEXT NOT NULL DEFAULT '',
    url_slug     TEXT NOT NULL DEFAULT '',
    image_name   TEXT NOT NULL DEFAULT '',
    logo_name    TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    server_ts    TEXT NOT NULL,
    UNIQUE (user_id, slot_start)
);

-- "Stop the watch: waiting on <person>". The watch stops at once; Jai approves
-- or rejects. Rejected = that time counts as normal. depends_on_user_id is set
-- for a teammate, empty for an outside person (then only the name).
CREATE TABLE IF NOT EXISTS task_holds (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id            INTEGER NOT NULL,
    user_id            TEXT NOT NULL,
    depends_on_user_id TEXT,
    depends_on_name    TEXT NOT NULL,
    reason             TEXT NOT NULL,
    start_ts           TEXT NOT NULL,
    end_ts             TEXT,
    status             TEXT NOT NULL DEFAULT 'pending',
    decided_by         TEXT,
    decided_at         TEXT,
    decision_note      TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_th_one_open ON task_holds(task_id) WHERE end_ts IS NULL;

CREATE TABLE IF NOT EXISTS time_corrections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL,
    task_id        INTEGER,
    interval_id    INTEGER,
    field          TEXT NOT NULL,
    original_value TEXT NOT NULL DEFAULT '',
    new_value      TEXT NOT NULL,
    reason         TEXT NOT NULL,
    evidence_url   TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'pending',
    requested_by   TEXT NOT NULL,
    requested_at   TEXT NOT NULL,
    decided_by     TEXT,
    decided_at     TEXT,
    decision_note  TEXT NOT NULL DEFAULT ''
);

-- type: allowance (employee's own, 2 a month) | emergency | planned (both
-- superuser) | holiday (user_id '*', removed from the target). Cancelling
-- stamps cancelled_at; the row stays.
CREATE TABLE IF NOT EXISTS leave_calendar (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT NOT NULL,
    date           TEXT NOT NULL,
    type           TEXT NOT NULL,
    credited_hours REAL NOT NULL DEFAULT 0,
    reason         TEXT NOT NULL DEFAULT '',
    declared_by    TEXT NOT NULL,
    declared_at    TEXT NOT NULL,
    cancelled_by   TEXT,
    cancelled_at   TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_lc_active ON leave_calendar(user_id, date) WHERE cancelled_at IS NULL;

CREATE TABLE IF NOT EXISTS work_settings (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    value  TEXT NOT NULL,
    set_by TEXT NOT NULL,
    set_at TEXT NOT NULL
);

-- ref = 'task:<id>' or 'day:<date>' or 'month:<yyyy-mm>'; one award per rule per ref.
CREATE TABLE IF NOT EXISTS work_points (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    task_id    INTEGER,
    rule       TEXT NOT NULL,
    ref        TEXT NOT NULL,
    points     REAL NOT NULL,
    reason     TEXT NOT NULL DEFAULT '',
    awarded_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, rule, ref)
);

CREATE TABLE IF NOT EXISTS badges (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS badges_awarded (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    code       TEXT NOT NULL,
    ref        TEXT NOT NULL,
    awarded_by TEXT NOT NULL,
    awarded_at TEXT NOT NULL,
    UNIQUE (user_id, code, ref)
);
CREATE TABLE IF NOT EXISTS employee_of_month (
    month      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    score      REAL NOT NULL DEFAULT 0,
    note       TEXT NOT NULL DEFAULT '',
    chosen_by  TEXT NOT NULL,
    chosen_at  TEXT NOT NULL
);

-- Tasks v3 "Start my day": login = clock-in. status on_time | late (fixed at the
-- press). end_source button | set_later (the person said it the next login).
CREATE TABLE IF NOT EXISTS work_days (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    date       TEXT NOT NULL,
    start_at   TEXT NOT NULL,
    end_at     TEXT,
    status     TEXT NOT NULL DEFAULT 'on_time',
    end_source TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, date)
);

-- Tasks v3: Jai's predefined daily tasks. A blocked person jumps to one; it becomes
-- their own work_tasks row (details.routine_id). user_id '*' = everyone. Switched
-- off with active = 0, never deleted.
CREATE TABLE IF NOT EXISTS daily_routines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    category_id INTEGER REFERENCES task_categories(id),
    details     TEXT NOT NULL DEFAULT '{}',
    priority    TEXT NOT NULL DEFAULT 'P2',
    user_id     TEXT NOT NULL DEFAULT '*',
    active      INTEGER NOT NULL DEFAULT 1,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Tasks v3: Jai's hours for one date (everyone). Latest row per date wins; hours
-- NULL = back to the weekly hours. Written once, never changed.
CREATE TABLE IF NOT EXISTS day_hours (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    date   TEXT NOT NULL,
    hours  REAL,
    note   TEXT NOT NULL DEFAULT '',
    set_by TEXT NOT NULL,
    set_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_dh_date ON day_hours(date, id);

-- Tasks v3 hour credits: hours a person may be short in a month before they owe time.
-- user_id '*' = everyone; latest row per user wins, a person's own row beats '*'.
CREATE TABLE IF NOT EXISTS hour_allowance (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    hours   REAL NOT NULL,
    set_by  TEXT NOT NULL,
    set_at  TEXT NOT NULL
);

-- Tasks v3 Big Ideas: how to make Agentic AI Automation the most watched company
-- (social, ChatGPT, Gemini, Maps...). Open to everyone. Jai sets status; 'repeat' doesn't
-- count. 'assigned' made a work_tasks row (task_id) for the person applying it.
CREATE TABLE IF NOT EXISTS big_ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    month       TEXT NOT NULL,
    title       TEXT NOT NULL,
    channel     TEXT NOT NULL,
    idea        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    assigned_to TEXT,
    project     TEXT NOT NULL DEFAULT '',
    task_id     INTEGER,
    note        TEXT NOT NULL DEFAULT '',
    decided_by  TEXT,
    decided_at  TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bi_month ON big_ideas(month, user_id);

-- ---- guardrails: nothing in v2 is ever deleted
""" + "".join(
    f"CREATE TRIGGER IF NOT EXISTS g_{t}_nodelete BEFORE DELETE ON {t} "
    f"BEGIN SELECT RAISE(ABORT, 'tasks v2: {t} rows are never deleted'); END;\n" for t in V3_TABLES
) + "".join(
    # Written once, never changed: the trail, the proof, points, settings history, awards.
    f"CREATE TRIGGER IF NOT EXISTS g_{t}_noupdate BEFORE UPDATE ON {t} "
    f"BEGIN SELECT RAISE(ABORT, 'tasks v2: {t} rows are never changed'); END;\n"
    for t in ("task_events", "work_slots", "work_settings", "work_points", "badges_awarded", "employee_of_month",
              "day_hours", "hour_allowance")
) + """
-- An interval can only be CLOSED (end_ts set once, after start); never reopened or moved.
CREATE TRIGGER IF NOT EXISTS g_work_intervals_close BEFORE UPDATE ON work_intervals
WHEN OLD.end_ts IS NOT NULL OR NEW.end_ts IS NULL OR NEW.end_ts < OLD.start_ts
  OR NEW.user_id IS NOT OLD.user_id OR NEW.task_id IS NOT OLD.task_id OR NEW.type IS NOT OLD.type
  OR NEW.start_ts IS NOT OLD.start_ts OR NEW.is_manual IS NOT OLD.is_manual OR NEW.question IS NOT OLD.question
BEGIN SELECT RAISE(ABORT, 'tasks v2: an interval can only be closed once'); END;

-- A correction is decided once; the request itself never changes.
CREATE TRIGGER IF NOT EXISTS g_time_corrections_decide BEFORE UPDATE ON time_corrections
WHEN OLD.status <> 'pending' OR NEW.user_id IS NOT OLD.user_id OR NEW.field IS NOT OLD.field
  OR NEW.original_value IS NOT OLD.original_value OR NEW.new_value IS NOT OLD.new_value
  OR NEW.reason IS NOT OLD.reason OR NEW.requested_at IS NOT OLD.requested_at
  OR NEW.task_id IS NOT OLD.task_id OR NEW.interval_id IS NOT OLD.interval_id
BEGIN SELECT RAISE(ABORT, 'tasks v2: a correction is decided once and never edited'); END;

-- Leave can only be cancelled (once); who, when, type and credit never change.
CREATE TRIGGER IF NOT EXISTS g_leave_calendar_cancel BEFORE UPDATE ON leave_calendar
WHEN OLD.cancelled_at IS NOT NULL OR NEW.cancelled_at IS NULL OR NEW.user_id IS NOT OLD.user_id
  OR NEW.date IS NOT OLD.date OR NEW.type IS NOT OLD.type OR NEW.credited_hours IS NOT OLD.credited_hours
  OR NEW.declared_by IS NOT OLD.declared_by OR NEW.declared_at IS NOT OLD.declared_at
BEGIN SELECT RAISE(ABORT, 'tasks v2: leave can only be cancelled, once'); END;

-- A hold can be ended once and decided once; who, why and when it started never change.
CREATE TRIGGER IF NOT EXISTS g_task_holds_once BEFORE UPDATE ON task_holds
WHEN NEW.task_id IS NOT OLD.task_id OR NEW.user_id IS NOT OLD.user_id OR NEW.start_ts IS NOT OLD.start_ts
  OR NEW.depends_on_user_id IS NOT OLD.depends_on_user_id OR NEW.depends_on_name IS NOT OLD.depends_on_name
  OR NEW.reason IS NOT OLD.reason
  OR (OLD.end_ts IS NOT NULL AND NEW.end_ts IS NOT OLD.end_ts) OR NEW.end_ts < OLD.start_ts
  OR (OLD.status <> 'pending' AND NEW.status IS NOT OLD.status)
BEGIN SELECT RAISE(ABORT, 'tasks v2: a hold is ended once and decided once'); END;

-- A day is ended once; who, which day, when it started and late/on time never change.
-- Ended once; the one way back is Jai's reopen (end_source 'reopened', old end kept in task_events).
-- DROP first so a database made before reopen gets the new rule.
DROP TRIGGER IF EXISTS g_work_days_end;
CREATE TRIGGER g_work_days_end BEFORE UPDATE ON work_days
WHEN (OLD.end_at IS NOT NULL AND NOT (NEW.end_at IS NULL AND NEW.end_source = 'reopened'))
  OR (NEW.end_at IS NULL AND NEW.end_source IS NOT 'reopened') OR NEW.end_at < OLD.start_at
  OR NEW.user_id IS NOT OLD.user_id OR NEW.date IS NOT OLD.date OR NEW.start_at IS NOT OLD.start_at
  OR NEW.status IS NOT OLD.status
BEGIN SELECT RAISE(ABORT, 'tasks v3: a day is ended once'); END;

-- A task keeps who made it and when.
CREATE TRIGGER IF NOT EXISTS g_work_tasks_origin BEFORE UPDATE ON work_tasks
WHEN NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'tasks v2: who created a task never changes'); END;
"""

# Jai's categories (26 Oct): each says what MUST be filled in. Jai edits or adds more later.
_REASON = [{"key": "reason", "label": "Reason", "type": "text"}]
DEFAULT_CATEGORIES = [
    # (name, required fields, deadline in working days, dependency stop needs Jai)
    ("Article writing", [{"key": "website", "label": "Website name", "type": "text"}], 0, 0),
    ("Content writing", [{"key": "purpose", "label": "For", "type": "choice",
                          "options": ["Social media", "Backlinks"]}], 0, 0),
    ("Website development", [{"key": "page", "label": "Which page", "type": "text"},
                             {"key": "updates", "label": "What updates", "type": "text"}], 0, 0),
    ("New website development", [{"key": "website", "label": "Website / domain", "type": "text"}], 3, 1),
    ("Calling", _REASON, 0, 0),
    ("Follow-up", _REASON, 0, 0),
    ("Meeting", _REASON, 0, 0),
    ("Other (must describe)", [{"key": "description", "label": "What is it", "type": "text"}], 0, 0),
]

# Every number Jai can change from admin settings. A new setting = a new row.
DEFAULT_WORK_SETTINGS = {
    "timezone": "Asia/Kolkata",
    "daily_target_hours": 7,
    "week_hours": [7, 7, 7, 7, 7, 7, 0],          # v3: target per weekday, Monday first; Jai sets it, a date can override
    "working_days": [0, 1, 2, 3, 4, 5],          # Monday = 0; Sunday off
    "sunday_counts": True,                        # Sunday hours count toward the month
    "slot_minutes": 15,                           # proof every 15 minutes
    "leave_allowance_per_month": 2,               # employee's own leave days, besides Sunday
    "lock_past_days": True,                       # yesterday is read-only; correction request to Jai
    "breaks": {"short_minutes": 15, "short_per_day": 2, "lunch_minutes": 30, "lunch_per_day": 1},
    "signal": {"green_min": 95, "amber_min": 80},
    "points": {"task_accepted": 10, "on_time": 5, "high_priority_min": 5, "high_priority_max": 15,
               "daily_target": 5, "sunday_catchup_per_2h": 5, "sunday_catchup_cap": 20,
               "monthly_target": 50},
    "levels": [["Starter", 0], ["Consistent Contributor", 200], ["Skilled Specialist", 500],
               ["Problem Solver", 900], ["Automation Champion", 1400]],
    "leaderboard_visible": False,
    "day_late_after": "10:30",                    # v3: "Start my day" after this (IST) = late start, never a penalty
    # v3: why the watch stopped for a dependency (Jai, 27 Oct). No proof is asked in v3.
    "block_reasons": ["Credentials expired", "Document required", "Information required"],
    # v3 hour credits (Jai, 30 Oct): short hours beyond the allowance are made up on other days
    "credit_day_cap_hours": 9,                    # at most this much of a day counts toward credits
    "thinking_cap_minutes": 60,                   # Thinking counts as work up to this much a day
    "idle_grace_seconds": 60,                     # after a dependency stop / Waiting, start something within this
    "idea_channels": ["Social media", "Google search", "ChatGPT", "Google Gemini", "DeepSeek", "Grok",
                      "Perplexity", "Claude", "Copilot", "Google Maps", "Apple Maps", "Other"],
    "ideas_required": 1,                          # Big Ideas a month, everyone
    "ideas_for_nomination": 6,                    # counted ideas in a month = Employee of the Month nominee
}

DEFAULT_BADGES = [
    ("streak_7", "7-day streak", "Target hit 7 working days in a row"),
    ("streak_30", "30-day streak", "Target hit 30 working days in a row"),
    ("monthly_target", "Month done", "Hit the monthly hours target"),
    ("on_time_10", "Always on time", "10 tasks accepted on time in a month"),
    ("helper", "Unblocker", "Helped a teammate get unblocked"),
    ("automation", "Automation Champion", "An automation with measured time saved"),
    ("employee_of_month", "Employee of the Month", "Chosen by Jai"),
]

DEFAULT_TIERS = [("Bronze", 300), ("Silver", 600), ("Gold", 1000), ("Platinum", 1500)]
DEFAULT_TEMPLATES = [("seo_lead", "backlinks", 20), ("seo_lead", "blogs", 2),
                     ("seo_lead", "Social media post", 10)]


def today_ist():
    return datetime.now(IST).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path():
    p = settings.DB_PATH
    return p if os.path.isabs(p) else os.path.join(os.getcwd(), p)


def connect():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    # INSERT OR REPLACE deletes the old row; this makes that fire the v2
    # no-delete triggers, so "replace" is refused too.
    conn.execute("PRAGMA recursive_triggers=ON")
    _local.conn = conn
    return conn


def init_db():
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT MAX(version) v FROM dt_schema_version").fetchone()["v"] is None:
            conn.execute("INSERT INTO dt_schema_version VALUES (?,?,?)",
                         (settings.SCHEMA_VERSION, now_iso(), "initial install"))
        if conn.execute("SELECT COUNT(*) c FROM work_types").fetchone()["c"] == 0:
            for i, (name, marks, kind) in enumerate(DEFAULT_WORK_TYPES):
                conn.execute("INSERT INTO work_types(name, base_marks, active, sort_order, kind) "
                             "VALUES (?,?,1,?,?)", (name, marks, (i + 1) * 10, kind))
        conn.execute("INSERT INTO dt_settings(key, value, updated_by, updated_at) VALUES (?,?,?,?) "
                     "ON CONFLICT(key) DO NOTHING",
                     ("settings", json.dumps(DEFAULT_SETTINGS), "installer", now_iso()))
        # ---- schema 2 (T7): additive, idempotent
        conn.executescript(SCHEMA_2)
        for table, col, decl in ADD_COLUMNS:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_ideas_week ON ideas(week, user_id)")
        conn.execute("INSERT OR IGNORE INTO rag_settings(id, green_min, amber_min) VALUES (1, 90, 60)")
        if conn.execute("SELECT COUNT(*) c FROM reward_tiers").fetchone()["c"] == 0:
            conn.executemany("INSERT INTO reward_tiers(name, min_points) VALUES (?,?)", DEFAULT_TIERS)
        if conn.execute("SELECT COUNT(*) c FROM role_templates").fetchone()["c"] == 0:
            conn.executemany("INSERT INTO role_templates(role, unit, qty_per_week) VALUES (?,?,?)",
                             DEFAULT_TEMPLATES)
        if (conn.execute("SELECT MAX(version) v FROM dt_schema_version").fetchone()["v"] or 1) < 2:
            conn.execute("INSERT INTO dt_schema_version VALUES (?,?,?)",
                         (2, now_iso(), "task manager (T7): tasks, targets, points, tiers"))
    _migrate_v3(conn)
    return conn


def _migrate_v3(conn):
    """Schema 3 (Tasks v2): new tables only. Backs up first on an upgrade."""
    if conn.execute("SELECT MAX(version) v FROM dt_schema_version").fetchone()["v"] < 3:
        backup("pre-v3")
    with conn:
        conn.executescript(SCHEMA_3)
        if conn.execute("SELECT COUNT(*) c FROM task_categories").fetchone()["c"] == 0:
            conn.executemany("INSERT INTO task_categories(name, fields, deadline_workdays, hold_needs_approval, "
                             "sort_order, created_at) VALUES (?,?,?,?,?,?)",
                             [(n, json.dumps(f), d, h, (i + 1) * 10, now_iso())
                              for i, (n, f, d, h) in enumerate(DEFAULT_CATEGORIES)])
        if conn.execute("SELECT COUNT(*) c FROM work_settings").fetchone()["c"] == 0:
            conn.execute("INSERT INTO work_settings(value, set_by, set_at) VALUES (?,?,?)",
                         (json.dumps(DEFAULT_WORK_SETTINGS), "installer", now_iso()))
        conn.executemany("INSERT OR IGNORE INTO badges(code, name, description, sort_order) VALUES (?,?,?,?)",
                         [(c, n, d, (i + 1) * 10) for i, (c, n, d) in enumerate(DEFAULT_BADGES)])
        if conn.execute("SELECT MAX(version) v FROM dt_schema_version").fetchone()["v"] < 3:
            conn.execute("INSERT INTO dt_schema_version VALUES (?,?,?)",
                         (3, now_iso(), "tasks v2: timer, 15-min proof, hours targets (new tables only)"))


def rows(sql, args=()):
    return [dict(r) for r in connect().execute(sql, args)]


def one(sql, args=()):
    r = connect().execute(sql, args).fetchone()
    return dict(r) if r else None


def write(sql, args=()):
    conn = connect()
    with conn:
        cur = conn.execute(sql, args)
    return cur


# ------------------------------------------------------------- settings
def get_settings():
    r = one("SELECT value FROM dt_settings WHERE key='settings'")
    out = dict(DEFAULT_SETTINGS)
    try:
        out.update(json.loads(r["value"]) if r else {})
    except Exception:
        pass
    return out


def put_settings(cfg, actor):
    write("INSERT INTO dt_settings(key, value, updated_by, updated_at) VALUES ('settings',?,?,?) "
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, "
          "updated_at=excluded.updated_at", (json.dumps(cfg), actor, now_iso()))


# ------------------------------------------------------------- targets
def target_for(user_id, on_date, default):
    r = one("SELECT daily_marks_target t FROM user_targets WHERE user_id=? AND effective_from<=? "
            "ORDER BY effective_from DESC LIMIT 1", (str(user_id), on_date))
    return float(r["t"]) if r else float(default)


def set_target(user_id, target, effective_from, actor):
    write("INSERT INTO user_targets(user_id, daily_marks_target, effective_from, set_by) "
          "VALUES (?,?,?,?) ON CONFLICT(user_id, effective_from) DO UPDATE SET "
          "daily_marks_target=excluded.daily_marks_target, set_by=excluded.set_by",
          (str(user_id), float(target), effective_from, actor))


def all_targets():
    return rows("SELECT * FROM user_targets ORDER BY user_id, effective_from")


# ------------------------------------------------------------- backup
def backup(reason="manual"):
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(settings.BACKUP_DIR, f"daily_tracker-{stamp}-{reason}.db")
    tgt = sqlite3.connect(dest)
    with tgt:
        connect().backup(tgt)
    tgt.close()
    return dest
