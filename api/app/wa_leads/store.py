"""Read and write the funnel's SQLite leads file.

The funnel owns this file: it creates the schema and it is the only writer of
a lead row. This module adds exactly one thing — the pipeline status — and
touches nothing else. It never inserts a lead, never edits an answer a visitor
gave, and never deletes.

Concurrency: the funnel sets journal_mode=WAL on first run, so a listing here
does not block a submission arriving there, and the other way round. Both
processes run as www-data.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

STATUSES = ("new", "contacted", "on_hold", "converted", "rejected")
OPEN_STATUSES = ("new", "contacted", "on_hold")
CLOSED_STATUSES = ("converted", "rejected")

JSON_FIELDS = ("pain_points", "auto_services", "organic_channels", "inorganic_channels")

# Columns a caller may sort by. An allowlist, not a format string, because the
# value reaches an ORDER BY clause that cannot be parameterised.
SORTABLE = {
    "created_at": "created_at",
    "fit_score": "fit_score",
    "name": "name COLLATE NOCASE",
    "industry": "industry COLLATE NOCASE",
    "status": "status",
    "status_at": "status_at",
}


def db_path() -> Path:
    return Path(config.DB_PATH)


@contextmanager
def connect(readonly: bool = True):
    """Open the funnel's database.

    Read-only by default and via a file: URI, so a bug in a listing path cannot
    write. `immutable` is deliberately NOT set — the funnel is writing to this
    file continuously and immutable would hand us a stale snapshot.
    """
    path = db_path()
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if not readonly:
            conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def available() -> bool:
    """True if the funnel's database exists and has the columns we need. The
    dashboard must not 500 because a separate service has not been deployed."""
    try:
        if not db_path().exists():
            return False
        with connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(leads)")}
        return {"status", "status_note", "status_by", "status_at"} <= cols
    except sqlite3.Error:
        return False


def row_to_lead(row: sqlite3.Row) -> dict:
    lead = dict(row)
    for f in JSON_FIELDS:
        try:
            lead[f] = json.loads(lead.get(f) or "[]")
        except (TypeError, ValueError):
            lead[f] = []
    lead["qualified"] = bool(lead.get("qualified"))
    # One display field rather than making every caller reassemble it. The raw
    # parts stay in the database; this is presentation.
    lead["whatsapp"] = f"+{lead.pop('whatsapp_country_code', '')}{lead.pop('whatsapp_number', '')}"
    # Never leave the server. The hash is only useful for rate limiting, and
    # a CRM screen has no business showing it.
    lead.pop("ip_hash", None)
    return lead


def list_leads(
    status: str | None = None,
    qualified: bool | None = None,
    industry: str | None = None,
    search: str | None = None,
    days: int | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = 1,
    page_size: int = config.PAGE_SIZE_DEFAULT,
) -> dict:
    where, params = [], []

    if status:
        if status == "open":
            where.append(f"status IN ({','.join('?' * len(OPEN_STATUSES))})")
            params += list(OPEN_STATUSES)
        else:
            where.append("status = ?")
            params.append(status)
    if qualified is not None:
        where.append("qualified = ?")
        params.append(1 if qualified else 0)
    if industry:
        where.append("industry = ?")
        params.append(industry)
    if days:
        where.append("created_at >= ?")
        params.append(
            (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        )
    if search:
        # A person looking someone up types a name, part of an email, or the
        # last few digits of a number. LIKE over three columns covers all three
        # at this volume; at ten thousand leads this wants FTS instead.
        needle = f"%{search.strip()}%"
        where.append("(name LIKE ? OR email LIKE ? OR whatsapp_number LIKE ?)")
        params += [needle, needle, needle]

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    order = SORTABLE.get(sort, SORTABLE["created_at"])
    order_dir = "ASC" if str(direction).lower() == "asc" else "DESC"

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), config.PAGE_SIZE_MAX))
    offset = (page - 1) * page_size

    with connect() as conn:
        (total,) = conn.execute(f"SELECT COUNT(*) FROM leads {clause}", params).fetchone()
        rows = conn.execute(
            f"SELECT * FROM leads {clause} ORDER BY {order} {order_dir}, id DESC "
            f"LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    pages = max(1, (total + page_size - 1) // page_size)
    return {
        "leads": [row_to_lead(r) for r in rows],
        "total": total,
        "page": page,
        "pages": pages,
        "page_size": page_size,
    }


def get_lead(lead_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return None
        events = conn.execute(
            "SELECT created_at, from_status, to_status, note, actor "
            "FROM lead_status_events WHERE lead_id = ? ORDER BY created_at ASC, id ASC",
            (lead_id,),
        ).fetchall()
    lead = row_to_lead(row)
    lead["history"] = [dict(e) for e in events]
    return lead


def set_status(lead_id: int, status: str, note: str, actor: str) -> dict | None:
    """Move a lead, and record that it moved.

    The update and the history row go in one transaction: a status that changed
    without an event would be a silent edit, which is the thing the event table
    exists to prevent.
    """
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")

    with connect(readonly=False) as conn:
        row = conn.execute("SELECT status FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return None
        previous = row["status"]
        now = _now()
        conn.execute(
            "UPDATE leads SET status = ?, status_note = ?, status_by = ?, status_at = ? "
            "WHERE id = ?",
            (status, (note or "").strip()[:1000], actor, now, lead_id),
        )
        conn.execute(
            "INSERT INTO lead_status_events "
            "(lead_id, created_at, from_status, to_status, note, actor) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lead_id, now, previous, status, (note or "").strip()[:1000], actor),
        )
    return get_lead(lead_id)


def stats() -> dict:
    with connect() as conn:
        (total,) = conn.execute("SELECT COUNT(*) FROM leads").fetchone()
        counts = {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status")
        }
        (recent,) = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE created_at >= ?",
            ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds"),),
        ).fetchone()
        avg = conn.execute("SELECT AVG(fit_score) AS a FROM leads").fetchone()["a"]
        (qualified_total,) = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE qualified = 1"
        ).fetchone()
        (qualified_converted,) = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE qualified = 1 AND status = 'converted'"
        ).fetchone()

    converted = counts.get("converted", 0)
    rejected = counts.get("rejected", 0)
    decided = converted + rejected
    return {
        "total": total,
        "by_status": [{"status": s, "count": counts.get(s, 0)} for s in STATUSES],
        "open_leads": sum(counts.get(s, 0) for s in OPEN_STATUSES),
        "converted": converted,
        "rejected": rejected,
        "conversion_rate": round(converted / decided * 100, 1) if decided else None,
        "qualified_total": qualified_total,
        "qualified_converted": qualified_converted,
        "last_7_days": recent,
        "average_fit_score": round(avg, 1) if avg is not None else None,
    }


def industries() -> list[str]:
    with connect() as conn:
        return [
            r["industry"]
            for r in conn.execute(
                "SELECT DISTINCT industry FROM leads WHERE industry != '' ORDER BY industry"
            )
        ]


def notifications(since_id: int = 0, limit: int = 10) -> dict:
    """Leads that arrived after `since_id`, newest first.

    Deliberately small: the dashboard polls this, so it carries the few fields
    a notification needs and nothing else. `latest_id` is the whole table's
    high-water mark, so a client that has seen it can stop asking for detail.
    """
    with connect() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM leads").fetchone()
        latest = row["m"]
        (unseen,) = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE id > ?", (since_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT id, created_at, name, industry, subtype, fit_score, qualified, status "
            "FROM leads WHERE id > ? ORDER BY id DESC LIMIT ?",
            (since_id, max(1, min(int(limit), 50))),
        ).fetchall()

    return {
        "latest_id": latest,
        "unseen": unseen,
        "leads": [
            {**dict(r), "qualified": bool(r["qualified"])} for r in rows
        ],
    }
