"""Backlink Ops — storage.

Deliberately a SEPARATE SQLite file, not a new set of tables inside the host
database. Three reasons, all of them continuity reasons:

  1. Nothing this module does can corrupt, lock or migrate existing data.
  2. Rollback is `rm` of one file plus one un-registered blueprint.
  3. Backup and restore of the feature is independent of the main backup.

The trade is that cross-feature SQL joins are not possible. That is the right
trade today; docs/SCALING.md describes the move to Postgres when it stops being.

Concurrency: WAL mode plus a short busy timeout. The expected load is three
people and a few hundred writes a day, which is two orders of magnitude inside
what this handles.
"""
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta

from .config import settings
from .seed import DEFAULT_CONFIG

IST = timezone(timedelta(hours=5, minutes=30))
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS bo_schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL,
    note        TEXT
);
CREATE TABLE IF NOT EXISTS bo_entries (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    date        TEXT NOT NULL,
    author      TEXT NOT NULL,
    url         TEXT NOT NULL,
    host        TEXT NOT NULL,
    type        TEXT NOT NULL,
    da          REAL NOT NULL DEFAULT 0,
    spam        REAL NOT NULL DEFAULT 0,
    follow      TEXT NOT NULL DEFAULT 'unknown',
    target      TEXT NOT NULL DEFAULT '',
    anchor      TEXT NOT NULL DEFAULT '',
    kw          TEXT NOT NULL DEFAULT '',
    relevant    INTEGER NOT NULL DEFAULT 0,
    indexed     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bo_entries_pd ON bo_entries(project, date);
CREATE INDEX IF NOT EXISTS ix_bo_entries_author ON bo_entries(author, date);

CREATE TABLE IF NOT EXISTS bo_reviews (
    entry_id    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    note        TEXT,
    reviewer    TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bo_queries (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    date        TEXT NOT NULL,
    author      TEXT NOT NULL,
    kw          TEXT NOT NULL,
    volume      INTEGER,
    kd          INTEGER,
    cpc         TEXT,
    verdict     TEXT,
    why         TEXT,
    raw         TEXT,
    source      TEXT NOT NULL DEFAULT 'ubersuggest',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bo_queries_pd ON bo_queries(project, date);

CREATE TABLE IF NOT EXISTS bo_bank (
    project     TEXT NOT NULL,
    kw          TEXT NOT NULL,
    volume      INTEGER,
    kd          INTEGER,
    cpc         TEXT,
    verdict     TEXT,
    why         TEXT,
    target_page TEXT,
    anchors     TEXT,
    link_plan   TEXT,
    author      TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (project, kw)
);

CREATE TABLE IF NOT EXISTS bo_coach (
    project     TEXT NOT NULL,
    date        TEXT NOT NULL,
    author      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (project, date, author)
);

CREATE TABLE IF NOT EXISTS bo_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_by  TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bo_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    role        TEXT NOT NULL,
    action      TEXT NOT NULL,
    target      TEXT,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS ix_bo_audit_at ON bo_audit(at);

CREATE TABLE IF NOT EXISTS bo_ai_usage (
    date        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    calls       INTEGER NOT NULL DEFAULT 0,
    failures    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, kind)
);
"""


def today_ist():
    return datetime.now(IST).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path():
    p = settings.DB_PATH
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    return p


def connect():
    """One connection per thread. Safe to call anywhere."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    _local.conn = conn
    return conn


def init_db(logger=None):
    """Idempotent. Creates the schema on first boot, records the version,
    and never alters anything outside the bo_ namespace."""
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT MAX(version) AS v FROM bo_schema_version")
        have = (cur.fetchone() or {})["v"]
        if have is None:
            conn.execute(
                "INSERT INTO bo_schema_version(version, applied_at, note) VALUES (?,?,?)",
                (settings.SCHEMA_VERSION, now_iso(), "initial install"))
        if conn.execute("SELECT COUNT(*) c FROM bo_config WHERE key='settings'").fetchone()["c"] == 0:
            conn.execute("INSERT INTO bo_config(key, value, updated_by, updated_at) VALUES (?,?,?,?)",
                         ("settings", json.dumps(DEFAULT_CONFIG), "installer", now_iso()))
    if logger:
        logger.info("[%s] schema v%s ready at %s",
                    settings.LOG_PREFIX, settings.SCHEMA_VERSION, db_path())
    return conn


def schema_version():
    try:
        row = connect().execute("SELECT MAX(version) v FROM bo_schema_version").fetchone()
        return row["v"] if row else None
    except Exception:
        return None


# ----------------------------------------------------------------- config
def get_config():
    row = connect().execute("SELECT value FROM bo_config WHERE key='settings'").fetchone()
    if not row:
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(row["value"])
    except Exception:
        return dict(DEFAULT_CONFIG)
    cfg.setdefault("level", 1)
    if not cfg.get("roster"):
        cfg["roster"] = DEFAULT_CONFIG["roster"]
    return cfg


def put_config(cfg, actor):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_config(key, value, updated_by, updated_at) VALUES ('settings',?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                     "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                     (json.dumps(cfg), actor, now_iso()))
    return cfg


# ----------------------------------------------------------------- entries
def add_entry(e):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO bo_entries(id,project,date,author,url,host,type,da,spam,follow,"
            "target,anchor,kw,relevant,indexed,created_at) VALUES "
            "(:id,:project,:date,:author,:url,:host,:type,:da,:spam,:follow,"
            ":target,:anchor,:kw,:relevant,:indexed,:created_at)", e)
    return e


def delete_entry(entry_id, project):
    conn = connect()
    with conn:
        cur = conn.execute("DELETE FROM bo_entries WHERE id=? AND project=?", (entry_id, project))
        conn.execute("DELETE FROM bo_reviews WHERE entry_id=?", (entry_id,))
    return cur.rowcount


def entries_for(project, date):
    rows = connect().execute(
        "SELECT * FROM bo_entries WHERE project=? AND date=? ORDER BY created_at", (project, date))
    return [_entry_row(r) for r in rows]


def _entry_row(r):
    d = dict(r)
    d["relevant"] = bool(d["relevant"])
    d["indexed"] = bool(d["indexed"])
    return d


def decisions_for(project, date):
    rows = connect().execute(
        "SELECT r.* FROM bo_reviews r JOIN bo_entries e ON e.id=r.entry_id "
        "WHERE e.project=? AND e.date=?", (project, date))
    return {r["entry_id"]: {"status": r["status"], "note": r["note"],
                            "by": r["reviewer"], "at": r["reviewed_at"]} for r in rows}


def set_decision(entry_id, status, note, reviewer):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_reviews(entry_id,status,note,reviewer,reviewed_at) "
                     "VALUES (?,?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET "
                     "status=excluded.status, note=excluded.note, reviewer=excluded.reviewer, "
                     "reviewed_at=excluded.reviewed_at",
                     (entry_id, status, note, reviewer, now_iso()))


def pending_entries(max_age_days=3, limit=500):
    """Links with no decision yet (or an explicit 'pending' one), newest last.
    Used by the auto-reviewer; older links are left to a human on purpose."""
    rows = connect().execute(
        "SELECT e.* FROM bo_entries e LEFT JOIN bo_reviews r ON r.entry_id = e.id "
        "WHERE (r.status IS NULL OR r.status = 'pending') "
        "AND e.date >= date('now', ?) ORDER BY e.created_at LIMIT ?",
        ("-%d day" % int(max_age_days), int(limit)))
    return [_entry_row(r) for r in rows]


def set_entry_follow(entry_id, follow):
    """The verifier saw the real rel attribute; record it so scoring uses the truth."""
    conn = connect()
    with conn:
        conn.execute("UPDATE bo_entries SET follow=? WHERE id=?", (follow, entry_id))


def get_meta(key, default=None):
    """Small JSON blobs beside the settings (last auto-review run, etc.).
    Lives in bo_config so no schema change is needed."""
    row = connect().execute("SELECT value FROM bo_config WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def put_meta(key, value, actor="system"):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_config(key, value, updated_by, updated_at) VALUES (?,?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                     "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                     (key, json.dumps(value), actor, now_iso()))


# ----------------------------------------------------------------- queries + bank
def add_query(q):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_queries(id,project,date,author,kw,volume,kd,cpc,verdict,why,"
                     "raw,source,created_at) VALUES (:id,:project,:date,:author,:kw,:volume,:kd,"
                     ":cpc,:verdict,:why,:raw,:source,:created_at)", q)
    return q


def queries_for(project, date):
    return [dict(r) for r in connect().execute(
        "SELECT * FROM bo_queries WHERE project=? AND date=? ORDER BY created_at", (project, date))]


def upsert_bank(rec):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO bo_bank(project,kw,volume,kd,cpc,verdict,why,target_page,anchors,"
            "link_plan,author,updated_at) VALUES (:project,:kw,:volume,:kd,:cpc,:verdict,:why,"
            ":target_page,:anchors,:link_plan,:author,:updated_at) "
            "ON CONFLICT(project,kw) DO UPDATE SET volume=excluded.volume, kd=excluded.kd, "
            "cpc=excluded.cpc, verdict=excluded.verdict, why=excluded.why, "
            "target_page=excluded.target_page, anchors=excluded.anchors, "
            "link_plan=excluded.link_plan, author=excluded.author, updated_at=excluded.updated_at",
            rec)
    return rec


def bank_for(project):
    out = []
    for r in connect().execute("SELECT * FROM bo_bank WHERE project=? ORDER BY updated_at", (project,)):
        d = dict(r)
        for k in ("anchors", "link_plan"):
            try:
                d[k] = json.loads(d[k]) if d[k] else []
            except Exception:
                d[k] = []
        out.append(d)
    return out


def bank_keywords(project):
    return [r["kw"] for r in connect().execute("SELECT kw FROM bo_bank WHERE project=?", (project,))]


# ----------------------------------------------------------------- coach
def put_coach(project, date, author, payload):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_coach(project,date,author,payload,created_at) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(project,date,author) DO UPDATE SET payload=excluded.payload, "
                     "created_at=excluded.created_at",
                     (project, date, author, json.dumps(payload), now_iso()))


def get_coach(project, date, author):
    r = connect().execute("SELECT payload FROM bo_coach WHERE project=? AND date=? AND author=?",
                          (project, date, author)).fetchone()
    if not r:
        return None
    try:
        return json.loads(r["payload"])
    except Exception:
        return None


# ----------------------------------------------------------------- history
def history(days_back=14):
    """Daily points per author per project, cheap enough to compute in SQL-free
    Python at this volume and immune to scoring drift because it re-scores."""
    from .scoring import score_entry
    rows = connect().execute(
        "SELECT * FROM bo_entries WHERE date >= date('now','-%d day') ORDER BY date" % int(days_back + 1))
    entries = [_entry_row(r) for r in rows]
    dec = {r["entry_id"]: r["status"] for r in connect().execute("SELECT entry_id, status FROM bo_reviews")}
    buckets = {}
    for e in entries:
        buckets.setdefault((e["project"], e["date"]), []).append(e)
    out = {}
    for (project, date), group in buckets.items():
        for e in group:
            if dec.get(e["id"]) == "rejected":
                continue
            key = (e["author"], project, date)
            out[key] = round(out.get(key, 0) + score_entry(e, group)["pts"], 1)
    qrows = connect().execute(
        "SELECT author, project, date, COUNT(*) c FROM bo_queries "
        "WHERE date >= date('now','-%d day') GROUP BY author, project, date" % int(days_back + 1))
    queries = {(r["author"], r["project"], r["date"]): r["c"] for r in qrows}
    return out, queries


# ----------------------------------------------------------------- ai usage
def bump_ai(kind, failed=False):
    conn = connect()
    with conn:
        conn.execute("INSERT INTO bo_ai_usage(date,kind,calls,failures) VALUES (?,?,1,?) "
                     "ON CONFLICT(date,kind) DO UPDATE SET calls=calls+1, failures=failures+?",
                     (today_ist(), kind, 1 if failed else 0, 1 if failed else 0))


def ai_calls_today():
    r = connect().execute("SELECT COALESCE(SUM(calls),0) c FROM bo_ai_usage WHERE date=?",
                          (today_ist(),)).fetchone()
    return r["c"] if r else 0


# ----------------------------------------------------------------- backup
def backup(reason="manual"):
    """Online backup using SQLite's own backup API — safe while the app runs."""
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(settings.BACKUP_DIR, f"backlink_ops-{stamp}-{reason}.db")
    src = connect()
    tgt = sqlite3.connect(dest)
    with tgt:
        src.backup(tgt)
    tgt.close()
    return dest


def prune_backups(keep=30):
    try:
        files = sorted(
            (os.path.join(settings.BACKUP_DIR, f) for f in os.listdir(settings.BACKUP_DIR)
             if f.endswith(".db")), key=os.path.getmtime)
    except FileNotFoundError:
        return 0
    removed = 0
    for f in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(f); removed += 1
        except OSError:
            pass
    return removed


def integrity_ok():
    try:
        r = connect().execute("PRAGMA integrity_check").fetchone()
        return (r[0] if r else "") == "ok"
    except Exception:
        return False
