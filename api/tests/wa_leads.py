"""Tests for the WhatsApp leads desk (app/wa_leads).

Needs no Postgres and no running funnel: it builds a throwaway SQLite file with
the funnel's schema, points the module at it, and exercises the store directly.

Run from the api/ directory:
    python tests/wa_leads.py

Exits non-zero on any failure, so it works as a deploy gate.
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TMP = Path(tempfile.mkdtemp()) / "leads.db"
os.environ.update({
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "JWT_SECRET_KEY": "x", "INITIAL_OWNER_EMAIL": "a@b.co",
    "INITIAL_OWNER_PASSWORD": "x", "CORS_ORIGINS": "http://localhost",
    "WA_LEADS_ENABLED": "1", "WA_LEADS_DB": str(TMP),
})
sys.path.insert(0, os.path.abspath("."))

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not condition:
        failures.append(name)


# A stand-in for the funnel's database. Mirrors store.SCHEMA in wa-funnel; if
# that file changes shape, this is the test that should start failing.
SCHEMA = """
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL, name TEXT NOT NULL,
    whatsapp_country_code TEXT NOT NULL, whatsapp_number TEXT NOT NULL,
    email TEXT NOT NULL, language TEXT NOT NULL, need_type TEXT NOT NULL,
    industry TEXT NOT NULL, subtype TEXT NOT NULL,
    pain_points TEXT NOT NULL DEFAULT '[]', auto_services TEXT NOT NULL DEFAULT '[]',
    organic_channels TEXT NOT NULL DEFAULT '[]', inorganic_channels TEXT NOT NULL DEFAULT '[]',
    website_status TEXT NOT NULL, fit_score INTEGER NOT NULL, qualified INTEGER NOT NULL,
    consent_at TEXT, utm_source TEXT NOT NULL DEFAULT '', utm_medium TEXT NOT NULL DEFAULT '',
    utm_campaign TEXT NOT NULL DEFAULT '', referrer TEXT NOT NULL DEFAULT '',
    ip_hash TEXT NOT NULL DEFAULT '', notified_at TEXT,
    status TEXT NOT NULL DEFAULT 'new', status_note TEXT NOT NULL DEFAULT '',
    status_by TEXT NOT NULL DEFAULT '', status_at TEXT
);
CREATE TABLE lead_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES leads(id),
    created_at TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT ''
);
"""


def seed():
    conn = sqlite3.connect(TMP)
    conn.executescript(SCHEMA)
    now = datetime.now(timezone.utc)
    rows = [
        ("Priya Menon", "91", "9876543210", "priya@brightlabel.in", "ecommerce",
         "D2C brand", 73, 1, "new", 0),
        ("Raj Kumar", "971", "501234567", "raj@gulflogix.ae", "logistics",
         "3PL warehouse operator", 81, 1, "converted", 2),
        ("Sam Iyer", "91", "9000000001", "sam@clinic.in", "healthcare",
         "Surgeon clinic", 45, 0, "rejected", 5),
        ("Dev Shah", "65", "81234567", "dev@fintech.sg", "bfsi",
         "Fintech", 66, 1, "on_hold", 9),
        ("Mia Chen", "91", "9000000002", "mia@retail.in", "other",
         "Retail chain / store", 31, 0, "new", 40),
    ]
    for name, cc, num, email, industry, subtype, score, qual, status, age in rows:
        conn.execute(
            "INSERT INTO leads (created_at, name, whatsapp_country_code, whatsapp_number,"
            " email, language, need_type, industry, subtype, pain_points, auto_services,"
            " website_status, fit_score, qualified, consent_at, utm_source, status, ip_hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ((now - timedelta(days=age)).isoformat(timespec="seconds"), name, cc, num,
             email, "English", "automation", industry, subtype,
             json.dumps(["orders"]), json.dumps(["rpa"]),
             "needs_work", score, qual, now.isoformat(timespec="seconds"), "meta",
             status, "deadbeef"),
        )
    conn.commit()
    conn.close()


seed()

from app.wa_leads import store  # noqa: E402

check("database is detected as available", store.available())

# ---------------------------------------------------------------- listing
page = store.list_leads()
check("lists every lead", page["total"] == 5, f"got {page['total']}")
check("newest first by default", page["leads"][0]["name"] == "Priya Menon",
      page["leads"][0]["name"])

check("filters by status", store.list_leads(status="converted")["total"] == 1)
check("'open' means everything undecided",
      store.list_leads(status="open")["total"] == 3,
      str(store.list_leads(status="open")["total"]))
check("filters by qualified", store.list_leads(qualified=True)["total"] == 3)
check("filters by industry", store.list_leads(industry="healthcare")["total"] == 1)
check("filters by age", store.list_leads(days=30)["total"] == 4)

check("search matches a name", store.list_leads(search="priya")["total"] == 1)
check("search matches an email fragment", store.list_leads(search="gulflogix")["total"] == 1)
check("search matches trailing digits", store.list_leads(search="543210")["total"] == 1)
check("search that matches nothing returns nothing",
      store.list_leads(search="zzzznope")["total"] == 0)

top = store.list_leads(sort="fit_score", direction="desc")["leads"][0]
check("sorts by fit score", top["fit_score"] == 81, str(top["fit_score"]))
low = store.list_leads(sort="fit_score", direction="asc")["leads"][0]
check("sorts ascending too", low["fit_score"] == 31, str(low["fit_score"]))

# An unknown sort key must fall back, never reach the SQL.
check("an unknown sort key falls back instead of injecting",
      store.list_leads(sort="; DROP TABLE leads; --")["total"] == 5)

paged = store.list_leads(page_size=2, page=2)
check("paginates", len(paged["leads"]) == 2 and paged["pages"] == 3,
      f"{len(paged['leads'])} rows, {paged['pages']} pages")
check("page size is capped",
      store.list_leads(page_size=9999)["page_size"] == store.config.PAGE_SIZE_MAX)

# ---------------------------------------------------------------- shaping
lead = page["leads"][0]
check("whatsapp is assembled for display", lead["whatsapp"] == "+919876543210",
      lead["whatsapp"])
check("the ip hash never leaves the server", "ip_hash" not in lead)
check("json columns come back as lists", lead["pain_points"] == ["orders"])
check("qualified is a bool", lead["qualified"] is True)

# ---------------------------------------------------------------- status moves
before = store.get_lead(1)
check("a fresh lead starts at new", before["status"] == "new")
check("a fresh lead has no history", before["history"] == [])

moved = store.set_status(1, "contacted", "Sent the intro on WhatsApp", "jai@example.co")
check("status is written", moved["status"] == "contacted")
check("the note is kept", moved["status_note"] == "Sent the intro on WhatsApp")
check("the actor is recorded", moved["status_by"] == "jai@example.co")
check("a timestamp is stamped", bool(moved["status_at"]))
check("the move is in the history", len(moved["history"]) == 1)
check("history records where it came from",
      moved["history"][0]["from_status"] == "new"
      and moved["history"][0]["to_status"] == "contacted")

store.set_status(1, "converted", "Signed", "jai@example.co")
again = store.get_lead(1)
check("history accumulates rather than replacing", len(again["history"]) == 2,
      str(len(again["history"])))
check("history is oldest first", again["history"][0]["to_status"] == "contacted")

try:
    store.set_status(1, "not_a_status", "", "jai@example.co")
    check("an unknown status is refused", False)
except ValueError:
    check("an unknown status is refused", True)

check("moving a lead that does not exist returns None",
      store.set_status(9999, "converted", "", "x@y.co") is None)
check("fetching a lead that does not exist returns None", store.get_lead(9999) is None)

# ---------------------------------------------------------------- read-only guard
try:
    with store.connect() as conn:          # default is read-only
        conn.execute("UPDATE leads SET name = 'nope' WHERE id = 1")
    check("the default connection cannot write", False)
except sqlite3.OperationalError:
    check("the default connection cannot write", True)

# ---------------------------------------------------------------- stats
s = store.stats()
check("counts everything", s["total"] == 5)
check("counts the open pipeline", s["open_leads"] == 2, str(s["open_leads"]))
check("counts conversions", s["converted"] == 2, str(s["converted"]))
# Decided = 2 converted + 1 rejected. Leads still in the pipeline are excluded.
check("conversion rate uses decided leads only", s["conversion_rate"] == 66.7,
      str(s["conversion_rate"]))
check("every status appears in the breakdown, including the empty ones",
      {r["status"] for r in s["by_status"]} == set(store.STATUSES))
check("reports the recent window", s["last_7_days"] == 3, str(s["last_7_days"]))
check("averages the fit score", s["average_fit_score"] == 59.2,
      str(s["average_fit_score"]))

check("lists the industries present",
      store.industries() == ["bfsi", "ecommerce", "healthcare", "logistics", "other"],
      str(store.industries()))

# ---------------------------------------------------------------- missing database
import importlib  # noqa: E402

os.environ["WA_LEADS_DB"] = str(TMP.parent / "does-not-exist.db")
importlib.reload(store.config)
importlib.reload(store)
check("a missing database is reported, not raised", store.available() is False)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("All wa_leads checks passed.")
