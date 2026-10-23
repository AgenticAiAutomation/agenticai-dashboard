"""Follow-ups (CRM) — end to end on a temp SQLite file with a fake login.

  * Jai's four follow-ups are seeded once, into an empty database only
  * "to do" = overdue first, then today by priority; upcoming; done newest first
  * every item carries contact details (tel / WhatsApp links) and the last log
  * done needs an outcome and can book the next step; snooze moves it a day
  * only owner/admin (or a superuser email) can use it; flag off = not mounted

Run:  PYTHONPATH="api;." python tests/test_followups.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = os.environ.setdefault("FU_TEST_TMP", tempfile.mkdtemp(prefix="fu-"))
os.environ.update({"FEATURE_FOLLOWUPS": "1", "FOLLOWUPS_DB": os.path.join(TMP, "fu.db"),
                   "FOLLOWUPS_USER_HOOK": "tests.test_followups:hook",
                   "FOLLOWUPS_SUPERUSERS": "contact@agenticaiautomation.co"})

USERS = {"jai": {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
         "boss": {"id": 2, "name": "Updesh", "email": "u@example.com", "role": "admin"},
         "akash": {"id": 7, "name": "Akash", "email": "akash@example.com", "role": "seo_lead"}}


def hook(request):
    return USERS.get(request.headers.get("x-user"))


PASS = 0


def check(label, cond):
    global PASS
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASS += 1


H = lambda w: {"x-user": w}  # noqa: E731
F = lambda d: d.strftime("%Y-%m-%dT%H:%M")  # noqa: E731


def app_with(flag="1"):
    os.environ["FEATURE_FOLLOWUPS"] = flag
    for m in [m for m in list(sys.modules) if m.startswith("app.followups")]:
        del sys.modules[m]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    ok = importlib.import_module("app.followups").register(app)
    return TestClient(app), ok


def main():
    c, ok = app_with()
    check("mounts with FEATURE_FOLLOWUPS=1", ok)
    names = {x["name"] for x in c.get("/api/followups/contacts", headers=H("jai")).json()["contacts"]}
    check("Jai's four contacts are seeded", {"Mr. Kaushik", "Mr. Vinod Aggarwal", "Aman", "Mr. Genpact"} <= names)
    cal = c.get("/api/followups/calendar?start=2026-10-20&end=2026-10-31", headers=H("jai")).json()["items"]
    by = {i["contact"]["name"]: i for i in cal}
    check("Kaushik: payment call Mon 26 Oct, P1", by["Mr. Kaushik"]["due_at"].startswith("2026-10-26")
          and by["Mr. Kaushik"]["kind"] == "payment" and by["Mr. Kaushik"]["priority"] == "P1")
    check("Vinod Aggarwal: meeting at their office, Mon 26 Oct", by["Mr. Vinod Aggarwal"]["kind"] == "meeting"
          and by["Mr. Vinod Aggarwal"]["location"] == "Their office")
    check("Aman (Hospital Cloud.ai): call Tue 27 Oct", by["Aman"]["due_at"].startswith("2026-10-27")
          and "Hospital Cloud.ai" in by["Aman"]["guide"])
    check("Genpact: Saturday 3 pm call about McDonald's", by["Mr. Genpact"]["due_at"] == "2026-10-24T15:00")
    check("each item reads as an instruction", by["Mr. Kaushik"]["guide"].startswith("Collect payment from Mr. Kaushik"))

    # restart: the seed must not come back twice
    c, _ = app_with()
    check("seed runs once", len(c.get("/api/followups/contacts", headers=H("jai")).json()["contacts"]) == 4)

    print("\n--- access ---")
    check("an associate can't open it", c.get("/api/followups/board", headers=H("akash")).status_code == 403)
    check("an admin can", c.get("/api/followups/board", headers=H("boss")).status_code == 200)
    check("signed out → 401", c.get("/api/followups/board").status_code == 401)

    print("\n--- to do order, contact details, logs ---")
    now = datetime.now() if False else None
    from app.followups import store
    now = store.now_ist()
    r = c.post("/api/followups/items", headers=H("jai"), json={
        "contact": {"name": "Ravi Mehta", "company": "Mehta Clinics", "phone": "98765 43210"},
        "kind": "call", "title": "Demo follow-up", "due_at": F(now - timedelta(days=2)), "priority": "P3"})
    check("new contact + follow-up in one step", r.status_code == 201)
    ravi = r.json()["followup"]
    check("phone becomes tel: and wa.me links (India +91)",
          ravi["contact"]["telLink"] == "tel:9876543210" and ravi["contact"]["waLink"] == "https://wa.me/919876543210")
    t1 = c.post("/api/followups/items", headers=H("jai"), json={"contact_id": ravi["contact_id"], "kind": "whatsapp",
                "title": "Send brochure", "due_at": F(now.replace(hour=23, minute=0)), "priority": "P2"}).json()["followup"]
    t2 = c.post("/api/followups/items", headers=H("jai"), json={"contact_id": ravi["contact_id"], "kind": "call",
                "title": "Confirm slot", "due_at": F(now.replace(hour=23, minute=30)), "priority": "P1"}).json()["followup"]
    b = c.get("/api/followups/board", headers=H("jai")).json()
    ids = [x["id"] for x in b["todo"]]
    check("overdue comes first", ids[0] == ravi["id"] and b["overdue"] >= 1)
    check("today is ordered by priority (P1 before P2)", ids.index(t2["id"]) < ids.index(t1["id"]))
    check("missing outcome refused", c.post(f"/api/followups/items/{ravi['id']}/done", headers=H("jai"),
                                            json={}).status_code == 400)
    d = c.post(f"/api/followups/items/{ravi['id']}/done", headers=H("jai"), json={
        "outcome": "Liked the demo; wants pricing for 3 clinics",
        "next": {"kind": "meeting", "title": "Pricing meeting", "due_at": F(now + timedelta(days=3)), "priority": "P1",
                 "location": "Mehta Clinics, Sector 14"}}).json()
    check("done + next step booked in one go", d["followup"]["status"] == "done" and d["next"]["prev_id"] == ravi["id"])
    b = c.get("/api/followups/board", headers=H("jai")).json()
    check("done list shows it, newest first", b["done"][0]["id"] == ravi["id"])
    nxt = [x for x in b["upcoming"] if x["id"] == d["next"]["id"]]
    check("the next step is upcoming, with the last meeting's log",
          nxt and nxt[0]["contact"]["lastLog"]["text"].startswith("Liked the demo"))
    c.post(f"/api/followups/contacts/{ravi['contact_id']}/notes", headers=H("jai"), json={"text": "Called back, asked for GST invoice"})
    ct = c.get(f"/api/followups/contacts/{ravi['contact_id']}", headers=H("jai")).json()["contact"]
    check("contact history: follow-ups + notes; newest log wins",
          len(ct["followups"]) == 4 and ct["lastLog"]["text"].startswith("Called back"))
    s = c.post(f"/api/followups/items/{t1['id']}/snooze", headers=H("jai"), json={}).json()["followup"]
    check("snooze moves it a day", s["due_at"][:10] == (now.date() + timedelta(days=1)).isoformat())
    u = c.put(f"/api/followups/items/{by['Mr. Genpact']['id']}", headers=H("jai"),
              json={"due_at": "2026-10-31T15:00"}).json()["followup"]
    check("a date can be changed (Genpact → 31 Oct if that was meant)", u["due_at"] == "2026-10-31T15:00")
    check("bad priority refused", c.post("/api/followups/items", headers=H("jai"), json={
        "contact_id": ravi["contact_id"], "title": "x y z", "due_at": "2026-11-01", "priority": "P9"}).status_code == 400)
    e = c.put(f"/api/followups/contacts/{ravi['contact_id']}", headers=H("jai"), json={"email": "ravi@mehta.in"})
    check("contact details editable", e.json()["contact"]["email"] == "ravi@mehta.in")

    print("\n--- projects + billing (Jai only) ---")
    due = (now.date() + timedelta(days=20)).isoformat()
    check("admins can't see projects/billing", c.get("/api/followups/projects", headers=H("boss")).status_code == 403)
    check("recurring needs a next payment date", c.post("/api/followups/projects", headers=H("jai"), json={
        "name": "DIYMart SEO retainer", "billing": "recurring"}).status_code == 400)
    pr = c.post("/api/followups/projects", headers=H("jai"), json={
        "name": "DIYMart SEO retainer", "site_id": "diymart", "billing": "recurring", "cycle": "monthly",
        "next_due": due, "amount_note": "Rs 25,000 + GST", "contact_id": ravi["contact_id"]}).json()["project"]
    rem = pr["reminder"]
    check("recurring project → payment follow-up 7 days before the due date",
          rem and rem["due_at"].startswith((now.date() + timedelta(days=13)).isoformat()) and rem["status"] == "open")
    cal = c.get(f"/api/followups/calendar?start={now.date().isoformat()}&end={due}", headers=H("jai")).json()["items"]
    item = [x for x in cal if x["id"] == rem["id"]][0]
    check("it reads as a P1 payment line with the plan", item["priority"] == "P1" and item["kind"] == "payment"
          and "monthly plan" in item["title"] and "DIYMart SEO retainer" in item["title"])
    adm = c.get(f"/api/followups/calendar?start={now.date().isoformat()}&end={due}", headers=H("boss")).json()["items"]
    check("…and admins don't see payment reminders", all(x["id"] != rem["id"] for x in adm))
    c.get("/api/followups/projects", headers=H("jai"))
    check("re-reading doesn't make a second reminder", len([x for x in c.get(
        f"/api/followups/calendar?start={now.date().isoformat()}&end={due}", headers=H("jai")).json()["items"]
        if "DIYMart SEO retainer" in x["title"]]) == 1)
    one = c.put(f"/api/followups/projects/{pr['id']}", headers=H("jai"), json={"billing": "one_time"}).json()["project"]
    check("switch to one-time → the reminder is cancelled", one["billing"] == "one_time" and one["reminder"]["status"] == "cancelled")
    back = c.put(f"/api/followups/projects/{pr['id']}", headers=H("jai"), json={"billing": "recurring"}).json()["project"]
    check("…and back to recurring → a reminder again", back["reminder"]["status"] == "open")
    paid = c.post(f"/api/followups/items/{back['reminder']['id']}/done", headers=H("jai"),
                  json={"outcome": "Paid by NEFT"}).json()
    nxt = c.get("/api/followups/projects", headers=H("jai")).json()["projects"][0]
    from datetime import date as _d
    expect = _d.fromisoformat(due)
    expect = expect.replace(month=expect.month % 12 + 1, year=expect.year + (expect.month == 12))
    check("marking it paid moves the next due date one month on", nxt["next_due"] == expect.isoformat())
    check("…and books the next reminder 7 days before that",
          nxt["reminder"] and nxt["reminder"]["status"] == "open" and nxt["reminder"]["due_at"].startswith(
              (expect - timedelta(days=7)).isoformat()))
    q = c.put(f"/api/followups/projects/{pr['id']}", headers=H("jai"), json={"cycle": "quarterly"}).json()["project"]
    check("cycle can change (quarterly)", q["cycle"] == "quarterly")
    np = c.post("/api/followups/projects", headers=H("jai"), json={"name": "Hospital Cloud website", "billing": "one_time"}).json()["project"]
    check("a one-time project with no customer gets a customer contact made", np["contact"]["name"].startswith("Hospital Cloud website"))
    check("admins can't change billing", c.put(f"/api/followups/projects/{pr['id']}", headers=H("boss"),
          json={"billing": "one_time"}).status_code == 403)

    c2, ok = app_with("0")
    check("flag off → not mounted", ok is False and c2.get("/api/followups/board", headers=H("jai")).status_code == 404)
    print(f"\nAll {PASS} follow-up checks passed.")


if __name__ == "__main__":
    main()
