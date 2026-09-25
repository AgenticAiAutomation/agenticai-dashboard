"""HTTP-level tests for the leads desk.

Auth is stubbed with FastAPI's dependency_overrides, so this needs no Postgres
and no token — it is the routing, permissions and response shapes under test,
not the dashboard's login.

Run from the api/ directory:
    python tests/wa_leads_api.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
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

conn = sqlite3.connect(TMP)
conn.executescript(SCHEMA)
conn.execute(
    "INSERT INTO leads (created_at, name, whatsapp_country_code, whatsapp_number, email,"
    " language, need_type, industry, subtype, pain_points, website_status, fit_score,"
    " qualified, consent_at, ip_hash)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (datetime.now(timezone.utc).isoformat(timespec="seconds"), "Priya Menon", "91",
     "9876543210", "priya@brightlabel.in", "Hinglish", "automation", "ecommerce",
     "D2C brand", json.dumps(["orders"]), "needs_work", 73, 1,
     datetime.now(timezone.utc).isoformat(timespec="seconds"), "deadbeef"),
)
conn.commit()
conn.close()

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


class FakeUser:
    def __init__(self, role, email):
        self.id = 1
        self.role = role
        self.email = email


def as_user(role, email="jai@example.co"):
    app.dependency_overrides[get_current_user] = lambda: FakeUser(role, email)
    return TestClient(app)


# ---------------------------------------------------------------- reading
c = as_user("admin")

r = c.get("/api/wa-leads")
check("list returns 200", r.status_code == 200, str(r.status_code))
body = r.json()
check("list returns the lead", body["total"] == 1, json.dumps(body)[:120])
check("list is paginated", body["page"] == 1 and body["pages"] == 1)

lead = body["leads"][0]
check("whatsapp is assembled", lead["whatsapp"] == "+919876543210", lead["whatsapp"])
check("ip hash is not in the response", "ip_hash" not in lead)
check("fit score is present for the team", lead["fit_score"] == 73)

r = c.get("/api/wa-leads/stats")
check("stats returns 200", r.status_code == 200)
check("stats counts the lead", r.json()["total"] == 1)
check("conversion rate is null with nothing decided",
      r.json()["conversion_rate"] is None)

r = c.get("/api/wa-leads/meta")
check("meta returns 200", r.status_code == 200)
check("meta lists the statuses", r.json()["statuses"][0] == "new")
check("meta reports the database is readable", r.json()["db_ok"] is True)
check("an admin may write", r.json()["can_write"] is True)

r = c.get("/api/wa-leads/1")
check("detail returns 200", r.status_code == 200)
check("detail carries an empty history", r.json()["history"] == [])

check("an unknown lead is a 404", c.get("/api/wa-leads/9999").status_code == 404)
check("an unknown status filter is a 422",
      c.get("/api/wa-leads?status=banana").status_code == 422)

# ---------------------------------------------------------------- writing
r = c.patch("/api/wa-leads/1/status", json={"status": "contacted", "note": "Said hello"})
check("an admin can move a lead", r.status_code == 200, str(r.status_code))
check("the new status comes back", r.json()["status"] == "contacted")
check("the actor is attributed", r.json()["status_by"] == "jai@example.co")
check("the move is recorded in history", len(r.json()["history"]) == 1)

r = c.patch("/api/wa-leads/1/status", json={"status": "banana"})
check("an invalid status is refused", r.status_code == 422, str(r.status_code))

check("moving an unknown lead is a 404",
      c.patch("/api/wa-leads/9999/status", json={"status": "converted"}).status_code == 404)

# ---------------------------------------------------------------- permissions
viewer = as_user("viewer", "reader@example.co")
check("a viewer can read", viewer.get("/api/wa-leads").status_code == 200)
check("a viewer is told they cannot write",
      viewer.get("/api/wa-leads/meta").json()["can_write"] is False)
r = viewer.patch("/api/wa-leads/1/status", json={"status": "converted"})
check("a viewer cannot write", r.status_code == 403, str(r.status_code))
check("the refusal explains itself", "not" in r.json()["detail"].lower())

# The viewer's blocked attempt must not have changed anything.
check("the blocked write changed nothing",
      as_user("admin").get("/api/wa-leads/1").json()["status"] == "contacted")

# ---------------------------------------------------------------- funnel absent
import importlib  # noqa: E402

from app.wa_leads import config as wl_config, store as wl_store  # noqa: E402

os.environ["WA_LEADS_DB"] = str(TMP.parent / "gone.db")
importlib.reload(wl_config)
importlib.reload(wl_store)
c = as_user("admin")
r = c.get("/api/wa-leads")
check("a missing funnel database is a 503, not a 500", r.status_code == 503, str(r.status_code))
check("the 503 says what is wrong and where",
      "wa-funnel" in r.json()["detail"], r.json().get("detail", "")[:80])
check("meta still answers so the page can render the reason",
      c.get("/api/wa-leads/meta").status_code == 200)
check("meta reports the database is not readable",
      c.get("/api/wa-leads/meta").json()["db_ok"] is False)

app.dependency_overrides.clear()

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("All wa_leads API checks passed.")
