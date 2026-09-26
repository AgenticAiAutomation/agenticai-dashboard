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
c = as_user("owner")

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
check("the owner may write", r.json()["can_write"] is True)

r = c.get("/api/wa-leads/1")
check("detail returns 200", r.status_code == 200)
check("detail carries an empty history", r.json()["history"] == [])

check("an unknown lead is a 404", c.get("/api/wa-leads/9999").status_code == 404)
check("an unknown status filter is a 422",
      c.get("/api/wa-leads?status=banana").status_code == 422)

# ---------------------------------------------------------------- writing
r = c.patch("/api/wa-leads/1/status", json={"status": "contacted", "note": "Said hello"})
check("the owner can move a lead", r.status_code == 200, str(r.status_code))
check("the new status comes back", r.json()["status"] == "contacted")
check("the actor is attributed", r.json()["status_by"] == "jai@example.co")
check("the move is recorded in history", len(r.json()["history"]) == 1)

r = c.patch("/api/wa-leads/1/status", json={"status": "banana"})
check("an invalid status is refused", r.status_code == 422, str(r.status_code))

check("moving an unknown lead is a 404",
      c.patch("/api/wa-leads/9999/status", json={"status": "converted"}).status_code == 404)

# ---------------------------------------------------------------- permissions
# The desk is owner-only. Every other role, including admin, is refused — and
# refused with a 404, so an account that may not see the desk cannot learn
# from the status code that a lead with a given id exists.
for role in ("admin", "seo_lead", "seo", "viewer"):
    other = as_user(role, f"{role}@example.co")
    check(f"{role} cannot list the desk",
          other.get("/api/wa-leads").status_code == 404,
          str(other.get("/api/wa-leads").status_code))
    check(f"{role} cannot read one lead",
          other.get("/api/wa-leads/1").status_code == 404)
    check(f"{role} cannot see the stats",
          other.get("/api/wa-leads/stats").status_code == 404)
    check(f"{role} cannot write",
          other.patch("/api/wa-leads/1/status",
                      json={"status": "converted"}).status_code == 404)

check("the refusal does not confirm the lead exists",
      as_user("admin").get("/api/wa-leads/1").json()["detail"] == "Not found.")

# A blocked attempt must not have changed anything.
check("the blocked writes changed nothing",
      as_user("owner").get("/api/wa-leads/1").json()["status"] == "contacted")

# Widening the gate is a config change, not a code change.
import importlib  # noqa: E402

from app.wa_leads import config as cfg_mod  # noqa: E402

os.environ["WA_LEADS_READ_ROLES"] = "owner,admin"
importlib.reload(cfg_mod)
import app.wa_leads.routes as routes_mod  # noqa: E402
routes_mod.config = cfg_mod
check("adding a role to WA_LEADS_READ_ROLES lets it read",
      as_user("admin").get("/api/wa-leads").status_code == 200)
check("but reading is still not writing",
      as_user("admin").patch("/api/wa-leads/1/status",
                             json={"status": "rejected"}).status_code == 403)
os.environ["WA_LEADS_READ_ROLES"] = "owner"
importlib.reload(cfg_mod)
routes_mod.config = cfg_mod
check("and taking it away closes the desk again",
      as_user("admin").get("/api/wa-leads").status_code == 404)

# ---------------------------------------------------------------- funnel absent
from app.wa_leads import config as wl_config, store as wl_store  # noqa: E402

os.environ["WA_LEADS_DB"] = str(TMP.parent / "gone.db")
importlib.reload(wl_config)
importlib.reload(wl_store)
c = as_user("owner")
r = c.get("/api/wa-leads")
check("a missing funnel database is a 503, not a 500", r.status_code == 503, str(r.status_code))
check("the 503 says what is wrong and where",
      "wa-funnel" in r.json()["detail"], r.json().get("detail", "")[:80])
check("meta still answers so the page can render the reason",
      c.get("/api/wa-leads/meta").status_code == 200)
check("meta reports the database is not readable",
      c.get("/api/wa-leads/meta").json()["db_ok"] is False)



# ---------------------------------------------------------------- bell
os.environ["WA_LEADS_DB"] = str(TMP)
importlib.reload(wl_config)
importlib.reload(wl_store)
c = as_user("owner")

r = c.get("/api/wa-leads/notifications?since_id=0")
check("notifications returns 200", r.status_code == 200, str(r.status_code))
n = r.json()
check("reports the high-water mark", n["latest_id"] == 1, str(n["latest_id"]))
check("counts what the client has not seen", n["unseen"] == 1, str(n["unseen"]))
check("carries the lead", n["leads"][0]["name"] == "Priya Menon")
check("carries the fit score for the badge", n["leads"][0]["fit_score"] == 73)

seen = c.get("/api/wa-leads/notifications?since_id=1").json()
check("nothing unseen once the client has caught up", seen["unseen"] == 0)
check("and no rows to render", seen["leads"] == [])

check("a non-owner gets nothing to poll",
      as_user("seo").get("/api/wa-leads/notifications").status_code == 404)

app.dependency_overrides.clear()

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("All wa_leads API checks passed.")
