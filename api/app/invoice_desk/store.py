"""Invoice Desk — storage.

A SEPARATE SQLite file (like Backlink Ops): nothing here can lock, migrate or
corrupt the dashboard's Postgres, rollback is one un-registered router, and
the invoice book backs up on its own. Every issue takes an online backup
first, because issued invoices are legal records.

Numbering: an invoice gets its number only at the moment it is issued, inside
one IMMEDIATE transaction that reads and bumps the counter, so numbers are
sequential with no gaps and no duplicates (UNIQUE index as the backstop).
"""
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .config import settings

IST = timezone(timedelta(hours=5, minutes=30))
_local = threading.local()

DEFAULT_SETTINGS = {
    "seller": {
        "name": "Agentic Biz Technologies",
        "tagline": "RPA | WEBSITES | WHATSAPP AUTOMATION\nLEAD GENERATION & BUSINESS OPERATIONS",
        "gstin": "06IGUPK9214G1ZV",
        "state_code": "06",
        "email": "Contact@AgenticAiAutomation.co",
        "phone": "",
        "address": "",
    },
    # Blank on the sample too. Fill on the desk (Settings) before issuing.
    "bank": {"account_name": "Agentic Biz Technologies", "account_no": "", "ifsc": "",
             "bank_name": "", "upi": ""},
    "numbering": {"prefix": "AI-", "next": 102},     # AI-101 was issued 25 Sep 2026
    "defaults": {"payment_terms": "Immediate / Net 15 Days", "tax_rate": "18",
                 "notes": ""},
    # Price list: picking an item on the desk fills its SAC and rate.
    # Edited under Settings → Price list. Seeded from money.CATALOG.
    "catalog": None,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS inv_schema_version (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS inv_settings (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_by TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inv_links (
    token       TEXT PRIMARY KEY,
    label       TEXT NOT NULL DEFAULT '',
    client_hint TEXT NOT NULL DEFAULT '',
    show_prices INTEGER NOT NULL DEFAULT 0,
    max_uses    INTEGER NOT NULL DEFAULT 1,
    uses        INTEGER NOT NULL DEFAULT 0,
    revoked     INTEGER NOT NULL DEFAULT 0,
    expires_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inv_invoices (
    id          TEXT PRIMARY KEY,
    number      TEXT,
    status      TEXT NOT NULL,          -- submitted | draft | issued | void
    source      TEXT NOT NULL,          -- link | desk
    link_token  TEXT,
    data        TEXT NOT NULL,          -- client, items, discount, tax, dates, notes
    totals      TEXT NOT NULL,
    snapshot    TEXT,                   -- seller + bank frozen at issue time
    void_reason TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    issued_at   TEXT,
    issued_by   TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inv_number ON inv_invoices(number) WHERE number IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_inv_status ON inv_invoices(status, updated_at);
CREATE TABLE IF NOT EXISTS inv_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, target TEXT, detail TEXT);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_ist():
    return datetime.now(IST).strftime("%Y-%m-%d")


def db_path():
    p = settings.DB_PATH
    return p if os.path.isabs(p) else os.path.join(os.getcwd(), p)


def connect():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    _local.conn = conn
    return conn


def init_db():
    c = connect()
    c.executescript(SCHEMA)
    if c.execute("SELECT MAX(version) v FROM inv_schema_version").fetchone()["v"] is None:
        c.execute("INSERT INTO inv_schema_version VALUES (?,?,?)",
                  (settings.SCHEMA_VERSION, now_iso(), "initial install"))
    if not c.execute("SELECT 1 FROM inv_settings WHERE key='settings'").fetchone():
        c.execute("INSERT INTO inv_settings VALUES ('settings',?,?,?)",
                  (json.dumps(DEFAULT_SETTINGS), "installer", now_iso()))


def integrity_ok():
    try:
        return connect().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except Exception:
        return False


# ---------------------------------------------------------------- settings
def get_settings():
    row = connect().execute("SELECT value FROM inv_settings WHERE key='settings'").fetchone()
    cfg = json.loads(row["value"]) if row else {}
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    if not out.get("catalog"):
        from .money import CATALOG
        out["catalog"] = [dict(c) for c in CATALOG]
    return out


def put_settings(cfg, actor):
    connect().execute(
        "INSERT INTO inv_settings VALUES ('settings',?,?,?) ON CONFLICT(key) DO UPDATE SET "
        "value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
        (json.dumps(cfg), actor, now_iso()))


# ---------------------------------------------------------------- links
def new_token():
    return secrets.token_urlsafe(24)


def add_link(rec):
    connect().execute(
        "INSERT INTO inv_links(token,label,client_hint,show_prices,max_uses,uses,revoked,"
        "expires_at,created_by,created_at) VALUES (:token,:label,:client_hint,:show_prices,"
        ":max_uses,0,0,:expires_at,:created_by,:created_at)", rec)
    return rec


def get_link(token):
    r = connect().execute("SELECT * FROM inv_links WHERE token=?", (token,)).fetchone()
    return dict(r) if r else None


def list_links(limit=100):
    return [dict(r) for r in connect().execute(
        "SELECT * FROM inv_links ORDER BY created_at DESC LIMIT ?", (limit,))]


def revoke_link(token):
    return connect().execute("UPDATE inv_links SET revoked=1 WHERE token=?", (token,)).rowcount


def link_usable(link):
    if not link or link["revoked"]:
        return False, "This link has been switched off. Ask us for a new one."
    if link["uses"] >= link["max_uses"]:
        return False, "This link has already been used. Ask us for a new one."
    if link["expires_at"] < now_iso():
        return False, "This link has expired. Ask us for a new one."
    return True, ""


def submit_via_link(token, inv):
    """Consume one use and store the submission atomically, so a link set to
    one use can never produce two invoices (double-click, two tabs)."""
    c = connect()
    c.execute("BEGIN IMMEDIATE")
    try:
        link = get_link(token)
        ok, why = link_usable(link)
        if not ok:
            c.execute("ROLLBACK")
            return None, why
        c.execute("UPDATE inv_links SET uses=uses+1 WHERE token=?", (token,))
        _insert(c, inv)
        c.execute("COMMIT")
        return inv, ""
    except Exception:
        c.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------- invoices
def _insert(c, inv):
    c.execute(
        "INSERT INTO inv_invoices(id,number,status,source,link_token,data,totals,snapshot,"
        "void_reason,created_at,updated_at,issued_at,issued_by) VALUES "
        "(:id,NULL,:status,:source,:link_token,:data,:totals,NULL,NULL,:created_at,"
        ":updated_at,NULL,NULL)",
        {**inv, "data": json.dumps(inv["data"]), "totals": json.dumps(inv["totals"])})


def add_invoice(inv):
    _insert(connect(), inv)
    return inv


def _row(r):
    if not r:
        return None
    d = dict(r)
    for k in ("data", "totals", "snapshot"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def get_invoice(inv_id):
    return _row(connect().execute("SELECT * FROM inv_invoices WHERE id=?", (inv_id,)).fetchone())


def list_invoices(statuses, limit=300):
    marks = ",".join("?" * len(statuses))
    return [_row(r) for r in connect().execute(
        f"SELECT * FROM inv_invoices WHERE status IN ({marks}) ORDER BY "
        "COALESCE(issued_at, updated_at) DESC LIMIT ?", (*statuses, limit))]


def counts():
    return {r["status"]: r["c"] for r in connect().execute(
        "SELECT status, COUNT(*) c FROM inv_invoices GROUP BY status")}


def update_invoice(inv_id, data, totals, status=None):
    sets = "data=?, totals=?, updated_at=?" + (", status=?" if status else "")
    args = [json.dumps(data), json.dumps(totals), now_iso()] + ([status] if status else [])
    return connect().execute(
        f"UPDATE inv_invoices SET {sets} WHERE id=? AND status IN ('submitted','draft')",
        (*args, inv_id)).rowcount


def delete_invoice(inv_id):
    return connect().execute(
        "DELETE FROM inv_invoices WHERE id=? AND status IN ('submitted','draft')",
        (inv_id,)).rowcount


def issue_invoice(inv_id, data, totals, snapshot, actor):
    """Assign the next number and lock the invoice — one transaction."""
    c = connect()
    c.execute("BEGIN IMMEDIATE")
    try:
        row = c.execute("SELECT status FROM inv_invoices WHERE id=?", (inv_id,)).fetchone()
        if not row or row["status"] not in ("submitted", "draft"):
            c.execute("ROLLBACK")
            return None
        cfg = get_settings()
        num = cfg["numbering"]
        n = int(num.get("next") or 1)
        number = f"{num.get('prefix', '')}{n}"
        while c.execute("SELECT 1 FROM inv_invoices WHERE number=?", (number,)).fetchone():
            n += 1
            number = f"{num.get('prefix', '')}{n}"
        cfg["numbering"]["next"] = n + 1
        c.execute("UPDATE inv_settings SET value=?, updated_by=?, updated_at=? WHERE key='settings'",
                  (json.dumps(cfg), actor, now_iso()))
        c.execute("UPDATE inv_invoices SET number=?, status='issued', data=?, totals=?, snapshot=?, "
                  "issued_at=?, issued_by=?, updated_at=? WHERE id=?",
                  (number, json.dumps(data), json.dumps(totals), json.dumps(snapshot),
                   now_iso(), actor, now_iso(), inv_id))
        c.execute("COMMIT")
        return number
    except Exception:
        c.execute("ROLLBACK")
        raise


def void_invoice(inv_id, reason):
    return connect().execute(
        "UPDATE inv_invoices SET status='void', void_reason=?, updated_at=? "
        "WHERE id=? AND status='issued'", (reason, now_iso(), inv_id)).rowcount


# ---------------------------------------------------------------- audit + backup
def audit(actor, action, target=None, detail=None):
    try:
        connect().execute("INSERT INTO inv_audit(at,actor,action,target,detail) VALUES (?,?,?,?,?)",
                          (now_iso(), actor, action, target, json.dumps(detail or {})))
    except Exception:
        pass   # an audit hiccup must never block billing


def recent_audit(n=200):
    return [dict(r) for r in connect().execute(
        "SELECT * FROM inv_audit ORDER BY id DESC LIMIT ?", (n,))]


def backup(reason="manual"):
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(settings.BACKUP_DIR, f"invoice_desk-{stamp}-{reason}.db")
    tgt = sqlite3.connect(dest)
    with tgt:
        connect().backup(tgt)
    tgt.close()
    files = sorted((os.path.join(settings.BACKUP_DIR, f) for f in os.listdir(settings.BACKUP_DIR)
                    if f.endswith(".db")), key=os.path.getmtime)
    for f in files[:-settings.BACKUP_KEEP]:
        try:
            os.remove(f)
        except OSError:
            pass
    return dest
