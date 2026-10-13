"""Daily Tracker + Idea Board — end-to-end (temp SQLite, fake identity, no network).

Walks the spec's testing checklist (§5) for T4:
  log with proof → review queue → approve → marks; late = 50%; duplicate
  link blocked (also when written differently, and when it is already in
  Backlink Ops); only your own sites; target hit → done + streak; Backlink Ops
  links show up without re-entry and with capped marks; ideas → Worked →
  badge; votes; bulk review; report + CSV; both flags off → nothing mounted.

Run:  PYTHONPATH=api python tests/test_daily_tracker.py
"""
import importlib
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = os.environ.setdefault("DT_TEST_TMP", tempfile.mkdtemp(prefix="dt-"))
os.environ.update({
    "BACKLINK_OPS_ENABLED": "1", "BACKLINK_OPS_AI_PROVIDER": "none",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"), "BACKLINK_OPS_BACKUP_DIR": os.path.join(TMP, "bk"),
    "BACKLINK_OPS_USER_HOOK": "tests.test_daily_tracker:hook",
    "BACKLINK_OPS_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_ADMIN_ROLES": "admin,seo_lead,seo,owner",
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_daily_tracker:hook",
    "DAILY_TRACKER_SUPERUSERS": "contact@agenticaiautomation.co",
})

USERS = {
    "jai":   {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
    "akash": {"id": 7, "name": "Akash Yadav", "email": "akash0710yadav@gmail.com", "role": "seo_lead"},
    "a2":    {"id": 3, "name": "SEO Associate 2", "email": "seo2@agenticai.co", "role": "seo_lead"},
}


def hook(request):
    return USERS.get(request.headers.get("x-user"))


PASS = 0


def check(label, cond):
    global PASS
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASS += 1


def build(tracker="1", ideas="1"):
    os.environ["FEATURE_DAILY_TRACKER"], os.environ["FEATURE_IDEA_BOARD"] = tracker, ideas
    for name in [m for m in list(sys.modules)
                 if m.startswith("app.backlink_ops") or m.startswith("app.daily_tracker")]:
        del sys.modules[name]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    importlib.import_module("app.backlink_ops").register(app)
    mounted = importlib.import_module("app.daily_tracker").register(app)
    return TestClient(app), mounted


H = lambda who: {"x-user": who}  # noqa: E731


def main():
    c, mounted = build()
    check("tracker mounts with the flags on", mounted)
    c.put("/api/seo/backlink-ops/config", headers=H("jai"), json={"roster": [
        {"name": "Jai", "project": "agenticai", "owner": True},
        {"name": "Akash", "email": "akash0710yadav@gmail.com", "project": "whatsappauto"},
        {"name": "SEO Associate 2", "project": "diymart"}]})

    print("\n--- status and sites ---")
    s = c.get("/api/tasks/status", headers=H("akash")).json()
    check("Akash's sites come from the Backlink Ops roster", s["allowed"] == ["whatsappauto"])
    check("default daily target is 40", s["target"] == 40)
    check("Jai is a reviewer", c.get("/api/tasks/status", headers=H("jai")).json()["isAdmin"])
    types = {t["name"]: t for t in c.get("/api/tasks/work-types", headers=H("akash")).json()["types"]}
    check("the spec's 14 work types are seeded", len(types) == 14)
    blog_w, blog_p, other = (types["Blog article written"], types["Blog article published"],
                             types["Other (must describe)"])

    def log(who, **kw):
        body = {"project_id": "whatsappauto", "work_type_id": blog_w["id"],
                "proof_url": "https://whatsappautomation.co.in/blog/a", "note": "", "minutes": 60}
        body.update(kw)
        return c.post("/api/tasks/logs", headers=H(who), json=body)

    print("\n--- logging rules ---")
    r = log("akash")
    check("Akash logs 'Blog article written' with a link", r.status_code == 201)
    first = r.json()["log"]["id"]
    check("no proof link → refused", log("akash", proof_url="").status_code == 400)
    check("a proof that is not a URL → refused", log("akash", proof_url="my blog").status_code == 400)
    check("a site he is not on → refused", log("akash", project_id="diymart",
                                               proof_url="https://x.example/1").status_code == 400)
    check("'Other' without a description → refused",
          log("akash", work_type_id=other["id"], proof_url="https://x.example/2").status_code == 400)
    check("note over 300 characters → refused",
          log("akash", proof_url="https://x.example/3", note="x" * 301).status_code == 400)
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    check("a future date → refused", log("akash", proof_url="https://x.example/4", date=tomorrow).status_code == 400)
    old = (date.today() - timedelta(days=10)).isoformat()
    check("older than 7 days → refused", log("akash", proof_url="https://x.example/5", date=old).status_code == 400)
    d = log("akash", proof_url="HTTPS://www.WhatsAppAutomation.co.in/blog/a/?utm_source=x#top")
    check("the same link written differently is a duplicate (409)",
          d.status_code == 409 and d.json()["error"] == "duplicate")

    # a link that lives in Backlink Ops already
    e = c.post("/api/seo/backlink-ops/entries", headers=H("akash"), json={
        "project": "whatsappauto", "url": "https://forum.example/thread/9", "type": "forum", "da": 30,
        "spam": 1, "follow": "dofollow", "target": "/", "anchor": "here", "kw": "x"})
    check("(Akash logs a link on Backlink Ops)", e.status_code == 201)
    bo_id = e.json()["rows"][-1]["id"]
    check("logging a Backlink Ops link again here → refused",
          log("akash", work_type_id=types["Backlink built"]["id"],
              proof_url="https://forum.example/thread/9").status_code == 409)

    yesterday = (date.fromisoformat(s["today"]) - timedelta(days=1)).isoformat()
    late = log("akash", work_type_id=blog_p["id"], proof_url="https://whatsappautomation.co.in/blog/b",
               date=yesterday)
    check("yesterday's work logged today is accepted but marked late",
          late.status_code == 201 and late.json()["late"] is True)
    late_id = late.json()["log"]["id"]

    print("\n--- review and marks ---")
    q = c.get("/api/tasks/review-queue", headers=H("jai")).json()
    check("both logs wait in Jai's review queue", {first, late_id} <= {x["id"] for x in q["logs"]})
    check("an associate cannot open the queue", c.get("/api/tasks/review-queue", headers=H("akash")).status_code == 403)
    check("an associate cannot approve",
          c.post(f"/api/tasks/logs/{first}/review", headers=H("akash"),
                 json={"status": "approved"}).status_code == 403)
    a = c.post(f"/api/tasks/logs/{first}/review", headers=H("jai"), json={"status": "approved", "quality": 3})
    check("approve at quality 3 → full base marks (10)", a.json()["log"]["marks"] == 10)
    b = c.post(f"/api/tasks/logs/{late_id}/review", headers=H("jai"), json={"status": "approved", "quality": 5})
    check("late log at quality 5 → 20 × 1.5 × 50% = 15", b.json()["log"]["marks"] == 15)
    lq1 = log("akash", proof_url="https://x.example/q1").json()["log"]["id"]
    r1 = c.post(f"/api/tasks/logs/{lq1}/review", headers=H("jai"), json={"status": "approved", "quality": 1})
    check("quality 1 → 0 marks", r1.json()["log"]["marks"] == 0)
    fix = log("akash", proof_url="https://x.example/fix").json()["log"]["id"]
    c.post(f"/api/tasks/logs/{fix}/review", headers=H("jai"), json={"status": "needs_fix", "note": "wrong link"})
    u = c.put(f"/api/tasks/logs/{fix}", headers=H("akash"), json={"proof_url": "https://x.example/fixed"})
    check("a 'needs fix' log can be corrected and goes back to review",
          u.status_code == 200 and u.json()["log"]["status"] == "submitted")
    check("someone else's log cannot be edited",
          c.put(f"/api/tasks/logs/{fix}", headers=H("a2"), json={"note": "x"}).status_code == 404)

    print("\n--- Backlink Ops rows, no double entry ---")
    lst = c.get("/api/tasks/logs", headers=H("akash")).json()["logs"]
    bo_rows = [x for x in lst if x["source"] == "backlink_ops"]
    check("the Backlink Ops link shows in today's list automatically", len(bo_rows) == 1)
    sm = c.get("/api/tasks/summary?range=day", headers=H("akash")).json()
    check("...but earns nothing while it waits for review there", sm["todayTotals"]["bo_marks"] == 0)
    c.post("/api/seo/backlink-ops/review", headers=H("jai"),
           json={"project": "whatsappauto", "decisions": [{"id": bo_id, "status": "approved"}]})
    sm = c.get("/api/tasks/summary?range=day", headers=H("akash")).json()
    check("approved there → 'Backlink built' marks here (5)", sm["todayTotals"]["bo_marks"] == 5)
    for i in range(8):
        e = c.post("/api/seo/backlink-ops/entries", headers=H("akash"), json={
            "project": "whatsappauto", "url": f"https://dir{i}.example/x", "type": "directory", "da": 30,
            "spam": 1, "follow": "dofollow", "target": "/", "anchor": "here", "kw": "x"}).json()
        c.post("/api/seo/backlink-ops/review", headers=H("jai"), json={
            "project": "whatsappauto", "decisions": [{"id": e["rows"][-1]["id"], "status": "approved"}]})
    sm = c.get("/api/tasks/summary?range=day", headers=H("akash")).json()
    check("Backlink Ops marks are capped per day (9 links × 5 → 20)", sm["todayTotals"]["bo_marks"] == 20)

    print("\n--- target, confetti signal, streak ---")
    check("10 + 20 = 30 today, under the 40 target", sm["todayTotals"]["marks"] == 30 and not sm["todayTotals"]["done"])
    g = log("akash", work_type_id=types["Guest post"]["id"], proof_url="https://guest.example/p")
    c.post(f"/api/tasks/logs/{g.json()['log']['id']}/review", headers=H("jai"),
           json={"status": "approved", "quality": 3})
    sm = c.get("/api/tasks/summary?range=week", headers=H("akash")).json()
    check("a guest post (15) takes him to 45 ≥ 40 → target hit", sm["todayTotals"]["done"] is True)
    check("yesterday's 15 alone did not hit, so the streak is 1", sm["streak"] == 1)
    check("week view has 7 days", len(sm["series"]) == 7)
    check("he ranks #1 on the month leaderboard", sm["rank"] == 1)
    check("and #1 on whatsappautomation.co.in", sm["projectRanks"].get("whatsappauto") == 1)
    t = c.put("/api/tasks/targets", headers=H("jai"), json={"user_id": "7", "daily_marks_target": 10,
                                                           "effective_from": yesterday})
    check("Jai sets Akash's target to 10 from yesterday", t.status_code == 200)
    sm = c.get("/api/tasks/summary?range=month", headers=H("akash")).json()
    check("now yesterday counts as hit too → 2-day streak", sm["streak"] == 2 and sm["target"] == 10)

    print("\n--- bulk review, report, CSV ---")
    c.get("/api/tasks/status", headers=H("a2"))
    ids = []
    for i in range(3):
        ids.append(c.post("/api/tasks/logs", headers=H("a2"), json={
            "project_id": "diymart", "work_type_id": types["Social media post"]["id"],
            "proof_url": f"https://instagram.com/p/{i}", "minutes": 10}).json()["log"]["id"])
    bulk = c.post("/api/tasks/logs/review-bulk", headers=H("jai"),
                  json={"ids": ids, "status": "approved", "quality": 3})
    check("bulk approve 3 logs", bulk.json()["reviewed"] == 3)
    rep = c.get("/api/tasks/report", headers=H("jai")).json()
    people = {p["name"]: p for p in rep["people"]}
    check("report has per-person, per-project marks",
          people["SEO Associate 2"]["projects"]["diymart"]["marks"] == 6)
    check("report has % of days on target", people["Akash Yadav"]["daysHit"] == 2)
    csv = c.get("/api/tasks/export.csv", headers=H("jai"))
    check("CSV export downloads", csv.status_code == 200 and "text/csv" in csv.headers["content-type"])
    check("CSV has manual rows and the Backlink Ops roll-up",
          "instagram.com/p/0" in csv.text and "backlink_ops" in csv.text)
    check("associates cannot export", c.get("/api/tasks/export.csv", headers=H("a2")).status_code == 403)
    imp = c.post("/api/tasks/import", headers=H("jai"), json={"csv":
        "Email,Project,Work type,Link,Note,Minutes,Date\n"
        f"seo2@agenticai.co,diymart.in,Social media post,https://fb.com/p/1,from sheet,5,{yesterday}\n"
        f"nobody@x.co,diymart.in,Social media post,https://fb.com/p/2,,5,{yesterday}\n"})
    check("sheet import adds known people and reports the rest",
          imp.json()["added"] == 1 and imp.json()["skipped"][0]["row"] == 3)

    print("\n--- Idea Board ---")
    i = c.post("/api/ideas", headers=H("akash"), json={
        "project_id": "whatsappauto", "title": "WhatsApp demo video on home",
        "problem": "Visitors bounce", "idea": "Embed a 40-second demo above the fold",
        "expected_result": "+20% demo requests", "metric": "GA4 demo_request events"})
    check("Akash submits an idea for his site", i.status_code == 201)
    iid = i.json()["idea"]["id"]
    check("an idea for a site he is not on → refused",
          c.post("/api/ideas", headers=H("akash"), json={"project_id": "diymart", "title": "x" * 5,
                                                          "idea": "y" * 12}).status_code == 400)
    check("he cannot vote for his own idea", c.post(f"/api/ideas/{iid}/vote", headers=H("akash")).status_code == 400)
    check("he cannot mark it Worked",
          c.post(f"/api/ideas/{iid}/status", headers=H("akash"), json={"status": "worked"}).status_code == 403)
    check("Jai cannot mark Worked without saying the result",
          c.post(f"/api/ideas/{iid}/status", headers=H("jai"), json={"status": "worked"}).status_code == 400)
    w = c.post(f"/api/ideas/{iid}/status", headers=H("jai"),
               json={"status": "worked", "result_note": "+31 demo requests in 3 weeks"})
    check("Jai marks it Worked with the result", w.json()["idea"]["status"] == "worked")
    badges = c.get("/api/tasks/status", headers=H("akash")).json()["badges"]
    check("Akash now has this month's winner badge", len(badges) == 1 and badges[0]["kind"] == "idea_winner")
    check("an associate on another site does not see the idea",
          c.get("/api/ideas", headers=H("a2")).json()["ideas"] == [])
    v = c.post(f"/api/ideas/{iid}/vote", headers=H("jai"))
    check("someone else can 👍", v.json()["idea"]["votes"] == 1)
    v = c.post(f"/api/ideas/{iid}/vote", headers=H("jai"))
    check("a second click takes the 👍 back", v.json()["idea"]["votes"] == 0)
    c.post(f"/api/ideas/{iid}/status", headers=H("jai"), json={"status": "in_trial"})
    check("moving it off Worked removes the badge",
          c.get("/api/tasks/status", headers=H("akash")).json()["badges"] == [])

    print("\n--- flags ---")
    c2, mounted = build("0", "0")
    check("both flags off → not mounted", mounted is False)
    check("...and /api/tasks/status is a plain 404", c2.get("/api/tasks/status", headers=H("akash")).status_code == 404)
    c3, _ = build("1", "0")
    check("tracker on, ideas off → /api/ideas says disabled",
          c3.get("/api/ideas", headers=H("akash")).json().get("error") == "disabled")

    print(f"\nAll {PASS} tracker checks passed.")


if __name__ == "__main__":
    main()
