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
    return conn


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
