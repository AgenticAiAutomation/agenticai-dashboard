"""Follow-ups — storage: its own SQLite file (nothing else is touched)."""
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .config import settings

IST = timezone(timedelta(hours=5, minutes=30))
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS fu_schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS fu_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS crm_contacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    company    TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    whatsapp   TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    city       TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    lead_id    INTEGER,                       -- WhatsApp funnel lead, when it came from there
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_crm_contacts_name ON crm_contacts(lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_contacts_lead ON crm_contacts(lead_id) WHERE lead_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_followups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES crm_contacts(id),
    kind        TEXT NOT NULL DEFAULT 'call',    -- call | meeting | payment | whatsapp | email | other
    title       TEXT NOT NULL,                   -- what this is about
    due_at      TEXT NOT NULL,                   -- IST 'YYYY-MM-DDTHH:MM'
    all_day     INTEGER NOT NULL DEFAULT 0,
    priority    TEXT NOT NULL DEFAULT 'P2',      -- P1 urgent | P2 | P3
    location    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',    -- open | done | cancelled
    outcome     TEXT NOT NULL DEFAULT '',        -- what happened (the log)
    done_at     TEXT,
    done_by     TEXT,
    prev_id     INTEGER,                         -- the follow-up this one came out of
    created_by  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_crm_fu_due ON crm_followups(status, due_at);
CREATE INDEX IF NOT EXISTS ix_crm_fu_contact ON crm_followups(contact_id);

-- Projects and how they are billed (Jai only). recurring → a payment
-- follow-up 7 days before next_due; converting back to one_time cancels it.
CREATE TABLE IF NOT EXISTS crm_projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    site_id     TEXT NOT NULL DEFAULT '',        -- Backlink Ops website id, if it is one
    contact_id  INTEGER REFERENCES crm_contacts(id),
    billing     TEXT NOT NULL DEFAULT 'one_time', -- one_time | recurring
    cycle       TEXT NOT NULL DEFAULT 'monthly',  -- monthly | quarterly | half_yearly | yearly
    next_due    TEXT,                             -- 'YYYY-MM-DD'
    amount_note TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- The marketing team: who besides the superusers may use Follow-ups and Leads.
-- Removing someone sets removed_at; adding them again makes a new row.
CREATE TABLE IF NOT EXISTS fu_access (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    added_by   TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    removed_by TEXT,
    removed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fu_access_active ON fu_access(email) WHERE removed_at IS NULL;

CREATE TABLE IF NOT EXISTS crm_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES crm_contacts(id),
    text       TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def now_ist():
    return datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)


def stamp():
    """IST wall-clock time to the second, for logs (done_at, notes)."""
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")


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


# The four follow-ups Jai listed on 22 Oct 2026 (phones left blank to fill in).
SEED = [
    ({"name": "Mr. Kaushik"},
     {"kind": "payment", "title": "Call about the pending payment", "due_at": "2026-10-26T10:00",
      "priority": "P1"}),
    ({"name": "Mr. Vinod Aggarwal"},
     {"kind": "meeting", "title": "Ask for a meeting to discuss, at their office", "due_at": "2026-10-26T11:00",
      "priority": "P1", "location": "Their office"}),
    ({"name": "Aman", "company": "Hospital Cloud.ai"},
     {"kind": "call", "title": "Follow-up call", "due_at": "2026-10-27T11:00", "priority": "P2"}),
    ({"name": "Mr. Genpact"},
     {"kind": "call", "title": "Call at 3 pm to fix Saturday evening meeting at McDonald's",
      "due_at": "2026-10-24T15:00", "priority": "P1", "location": "McDonald's"}),
]


def init_db():
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT MAX(version) v FROM fu_schema_version").fetchone()["v"] is None:
            conn.execute("INSERT INTO fu_schema_version VALUES (1, ?, 'initial install')", (now_iso(),))
        # v1.1: follow-ups made by the system (payment reminders) carry a ref.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(crm_followups)")}
        if "ref" not in cols:
            conn.execute("ALTER TABLE crm_followups ADD COLUMN ref TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_fu_ref ON crm_followups(ref) WHERE ref IS NOT NULL")
        seeded = conn.execute("SELECT value FROM fu_meta WHERE key='seed_2026_10_22'").fetchone()
        empty = conn.execute("SELECT COUNT(*) c FROM crm_contacts").fetchone()["c"] == 0
        if settings.SEED and not seeded and empty:
            now = now_iso()
            for c, f in SEED:
                cur = conn.execute("INSERT INTO crm_contacts(name, company, created_by, created_at, updated_at) "
                                   "VALUES (?,?,?,?,?)", (c["name"], c.get("company", ""), "seed", now, now))
                conn.execute("INSERT INTO crm_followups(contact_id, kind, title, due_at, priority, location, "
                             "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (cur.lastrowid, f["kind"], f["title"], f["due_at"], f["priority"],
                              f.get("location", ""), "seed", now, now))
            conn.execute("INSERT INTO fu_meta VALUES ('seed_2026_10_22', ?)", (now,))
    return conn


def rows(sql, args=()):
    return [dict(r) for r in connect().execute(sql, args)]


def one(sql, args=()):
    r = connect().execute(sql, args).fetchone()
    return dict(r) if r else None


def write(sql, args=()):
    conn = connect()
    with conn:
        return conn.execute(sql, args)
