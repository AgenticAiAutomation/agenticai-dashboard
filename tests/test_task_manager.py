"""Task manager (T7) — the spec's §7.10 checklist, end to end.

  * a task can't save without every SMART field
  * a Backlink Ops entry counts toward the matching task, never twice; a rejected one stops counting
  * a monthly target splits into weekly/daily; a leave day is 0; Jai can edit a week
  * RAG turns Amber / Red at the right % and on overdue
  * Mirror shows the right points and the gap to the next tier
  * no weekly idea by Friday → that task is Red; submitting one clears it
  * the bonus is hidden from other users; only Jai edits tiers
  * viewers read but cannot change; approving gives on-time bonus and level XP

Run:  PYTHONPATH="api;." python tests/test_task_manager.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = os.environ.setdefault("TM_TEST_TMP", tempfile.mkdtemp(prefix="tm-"))
os.environ.update({
    "BACKLINK_OPS_ENABLED": "1", "BACKLINK_OPS_AI_PROVIDER": "none",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"), "BACKLINK_OPS_BACKUP_DIR": os.path.join(TMP, "bk"),
    "BACKLINK_OPS_USER_HOOK": "tests.test_task_manager:hook",
    "BACKLINK_OPS_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_ADMIN_ROLES": "admin,seo_lead,seo,owner",
    "FEATURE_PER_PROJECT_LEVELS": "1",
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_task_manager:hook",
    "DAILY_TRACKER_SUPERUSERS": "contact@agenticaiautomation.co",
    "FEATURE_DAILY_TRACKER": "1", "FEATURE_IDEA_BOARD": "1", "FEATURE_TASK_MANAGER": "1",
})

USERS = {
    "jai":    {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
    "boss":   {"id": 2, "name": "Updesh", "email": "updesh@example.com", "role": "admin"},
    "akash":  {"id": 7, "name": "Akash Yadav", "email": "akash0710yadav@gmail.com", "role": "seo_lead"},
    "priya":  {"id": 8, "name": "Priya Sharma", "email": "priya@example.com", "role": "seo_lead"},
    "intern": {"id": 9, "name": "Intern", "email": "intern@example.com", "role": "viewer"},
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


H = lambda who: {"x-user": who}  # noqa: E731
F = lambda d: d.strftime("%Y-%m-%dT%H:%M")  # noqa: E731


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    importlib.import_module("app.backlink_ops").register(app)
    assert importlib.import_module("app.daily_tracker").register(app)
    tm = importlib.import_module("app.daily_tracker.taskmgr")
    tm.BLOG_SOURCE = lambda uid, a, b: [{"slug": "uipath-for-ca-firms", "date": b}] if str(uid) == "7" else []
    c = TestClient(app)
    real_now = tm.now_ist()

    c.put("/api/seo/backlink-ops/config", headers=H("jai"), json={"roster": [
        {"name": "Jai", "project": "agenticai", "owner": True},
        {"name": "Akash", "email": "akash0710yadav@gmail.com", "project": "whatsappauto"},
        {"name": "Akash", "email": "akash0710yadav@gmail.com", "project": "agenticai"},
        {"name": "Priya Sharma", "project": "diymart"},
        {"name": "Intern", "email": "intern@example.com", "project": "diymart"}]})
    for w in USERS:
        c.get("/api/tasks/status", headers=H(w))
    st = c.get("/api/tasks/status", headers=H("jai")).json()
    check("status reports the task manager flag and Jai as superuser", st["taskManager"] and st["isSuperuser"])

    def task(**kw):
        body = {"title": "Build 5 backlinks for WA Auto", "description": "Five dofollow links to /pricing",
                "project_id": "whatsappauto", "goal": "rankings", "target_qty": 5, "unit": "backlinks",
                "proof_type": "link", "effort_hours": 6, "priority": "P1",
                "start_at": F(real_now - timedelta(days=1)), "due_at": F(real_now + timedelta(days=6)),
                "recurrence": "none", "assignees": ["7"]}
        body.update(kw)
        return c.post("/api/tasks/items", headers=H(kw.pop("_as", "boss")), json=body)

    print("\n--- SMART ---")
    for field in ("title", "description", "project_id", "goal", "target_qty", "unit", "proof_type",
                  "effort_hours", "start_at", "due_at", "priority", "assignees"):
        r = task(**{field: "" if field != "assignees" else []})
        if r.status_code != 400 or r.json().get("error") != "not_smart":
            check(f"won't save without {field}", False)
    check("won't save if any SMART field is empty (12 fields tried)", True)
    check("due before start is refused",
          task(due_at=F(real_now - timedelta(days=2))).json().get("error") == "not_smart")
    check("an associate can't create tasks", task(_as="akash").status_code == 403)
    r = task()
    check("a complete SMART task saves (admin)", r.status_code == 201)
    bl = r.json()["task"]
    check("default marks: 5 backlinks × 5 = 25", bl["marks"] == 25)

    print("\n--- sync: Backlink Ops → task, no double count ---")
    ids = []
    for i in range(3):
        e = c.post("/api/seo/backlink-ops/entries", headers=H("akash"), json={
            "project": "whatsappauto", "url": f"https://d{i}.example/x", "type": "directory", "da": 30,
            "spam": 1, "follow": "dofollow", "target": "/", "anchor": "wa", "kw": "x"}).json()
        ids.append(e["rows"][-1]["id"])
    c.post("/api/seo/backlink-ops/entries", headers=H("priya"), json={
        "project": "diymart", "url": "https://p.example/x", "type": "directory", "da": 30,
        "spam": 1, "follow": "dofollow", "target": "/", "anchor": "x", "kw": "x"})
    t = c.get(f"/api/tasks/items/{bl['id']}", headers=H("akash")).json()["task"]
    check("3 Backlink Ops links count as 3", t["progress"] == 3)
    c.get("/api/tasks/items", headers=H("akash"))
    t = c.get(f"/api/tasks/items/{bl['id']}", headers=H("akash")).json()["task"]
    check("reading again does not double count", t["progress"] == 3)
    check("proof links come from the source entries", all(e["proof_url"].startswith("https://d") for e in t["entries"]))
    c.post("/api/seo/backlink-ops/review", headers=H("jai"),
           json={"project": "whatsappauto", "decisions": [{"id": ids[0], "status": "rejected"}]})
    t = c.get(f"/api/tasks/items/{bl['id']}", headers=H("akash")).json()["task"]
    check("a rejected link stops counting (2)", t["progress"] == 2)
    check("manual progress refused on an auto task (no double entry)",
          c.post(f"/api/tasks/items/{bl['id']}/progress", headers=H("akash"),
                 json={"qty": 1, "proof_url": "https://x.example"}).status_code == 400)
    blog = task(title="Publish 1 UiPath blog for CA firms", description="One article on UiPath for CA firms",
                project_id="agenticai", unit="blogs", target_qty=1).json()["task"]
    t = c.get(f"/api/tasks/items/{blog['id']}", headers=H("akash")).json()["task"]
    check("a published blog counts toward the blog task", t["progress"] == 1
          and t["entries"][0]["proof_url"].endswith("/uipath-for-ca-firms"))
    types = {w["name"]: w["id"] for w in c.get("/api/tasks/work-types", headers=H("akash")).json()["types"]}
    soc = task(title="Post 3 social posts", description="Three LinkedIn posts on reminders",
               unit=f"wt:{types['Social media post']}", target_qty=3).json()["task"]
    lid = c.post("/api/tasks/logs", headers=H("akash"), json={
        "project_id": "whatsappauto", "work_type_id": types["Social media post"],
        "proof_url": "https://linkedin.com/posts/a1", "minutes": 10}).json()["log"]["id"]
    t = c.get(f"/api/tasks/items/{soc['id']}", headers=H("akash")).json()["task"]
    check("a daily log counts only once approved (0 while pending)", t["progress"] == 0)
    c.post(f"/api/tasks/logs/{lid}/review", headers=H("boss"), json={"status": "approved", "quality": 3})
    t = c.get(f"/api/tasks/items/{soc['id']}", headers=H("akash")).json()["task"]
    check("approved daily log → task progress 1", t["progress"] == 1)

    print("\n--- status flow, viewer, approval ---")
    check("a viewer can't move a task",
          c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("intern"), json={"status": "in_progress"}).status_code in (403, 404))
    check("blocked needs a reason",
          c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("akash"), json={"status": "blocked"}).status_code == 400)
    r = c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("akash"), json={"status": "blocked", "reason": "Waiting on site access"})
    check("assignee marks it blocked with a reason", r.json()["task"]["status"] == "blocked")
    c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("akash"), json={"status": "in_progress"})
    r = c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("akash"), json={"status": "submitted"})
    check("assignee submits", r.json()["task"]["status"] == "submitted")
    check("an associate can't approve",
          c.post(f"/api/tasks/items/{bl['id']}/approve", headers=H("akash"), json={"status": "approved"}).status_code == 403)
    q = c.get("/api/tasks/review-queue", headers=H("boss")).json()
    check("submitted task is in the review queue", any(x["id"] == bl["id"] for x in q.get("tasks", [])))
    r = c.post(f"/api/tasks/items/{bl['id']}/approve", headers=H("boss"), json={"status": "needs_fix", "note": "2 links are nofollow"})
    check("needs fix counts as rework", r.json()["task"]["rework"] == 1)
    c.post(f"/api/tasks/items/{bl['id']}/status", headers=H("akash"), json={"status": "submitted"})
    r = c.post(f"/api/tasks/items/{bl['id']}/approve", headers=H("boss"), json={"status": "approved", "quality": 4}).json()
    check("approve on time: 25 × 1.25 × 1.10 = 34.38 points", r["points"] == 34.38 and r["onTime"])
    lv = c.get("/api/seo/backlink-ops/levels", headers=H("akash")).json()["rows"]
    wa = [x for x in lv if x["project"] == "whatsappauto"][0]
    check("approved task marks go to Akash's level XP on WA Auto (T2)", wa["xp"] >= 34.38)

    print("\n--- RAG ---")
    rs = {"green_min": 90, "amber_min": 60}
    base_t = {"status": "in_progress", "target_qty": 10, "start_at": F(real_now - timedelta(hours=50)),
              "due_at": F(real_now + timedelta(hours=50))}
    check("40% of expected → Red", tm.task_rag(base_t, 2, real_now, rs)[0] == "red")
    check("80% of expected → Amber", tm.task_rag(base_t, 4, real_now, rs)[0] == "amber")
    check("≥90% → Green", tm.task_rag(base_t, 5, real_now, rs)[0] == "green")
    check("overdue → Red", tm.task_rag(dict(base_t, due_at=F(real_now - timedelta(hours=1))), 10, real_now, rs)[0] == "red")
    check("due within 24 h and not submitted → Amber",
          tm.task_rag(dict(base_t, due_at=F(real_now + timedelta(hours=3))), 10, real_now, rs)[0] == "amber")
    check("submitted → Green", tm.task_rag(dict(base_t, status="submitted"), 0, real_now, rs)[0] == "green")
    c.put("/api/tasks/rag-settings", headers=H("boss"), json={"green_min": 75, "amber_min": 50})
    check("thresholds editable: 80% is Green at 75/50",
          tm.task_rag(base_t, 4, real_now, tm._rag_settings())[0] == "green")
    c.put("/api/tasks/rag-settings", headers=H("boss"), json={"green_min": 90, "amber_min": 60})

    print("\n--- targets: month → weeks → days, leave ---")
    month = real_now.strftime("%Y-%m")
    wd = tm._workdays(month)
    r = c.put("/api/tasks/plan", headers=H("boss"),
              json={"user_id": "8", "project_id": "diymart", "unit": "backlinks", "month": month, "qty": len(wd) * 2})
    p = r.json()["targets"][0]
    check(f"monthly {len(wd) * 2} over {len(wd)} working days → 2 a working day",
          all(v == 2 for d, v in p["days"].items() if datetime.fromisoformat(d).date() in wd))
    check("Sundays get 0", all(v == 0 for d, v in p["days"].items() if datetime.fromisoformat(d).weekday() == 6))
    check("weeks add up to the month", round(sum(w["qty"] for w in p["weeks"])) == len(wd) * 2)
    leave_day = wd[len(wd) // 2].isoformat()
    c.put("/api/tasks/leave", headers=H("boss"), json={"user_id": "8", "date": leave_day, "reason": "sick"})
    p = c.get(f"/api/tasks/plan?user_id=8&month={month}", headers=H("boss")).json()["targets"][0]
    check("a leave day's target becomes 0 (not pushed onto other days)",
          p["days"][leave_day] == 0 and p["days"][wd[0].isoformat()] == 2)
    ws = p["weeks"][1]["weekStart"]
    p = c.put("/api/tasks/plan/split", headers=H("boss"), json={"user_id": "8", "project_id": "diymart",
              "unit": "backlinks", "month": month, "week_start": ws, "qty": 30}).json()["targets"][0]
    check("Jai edits one week's split", [w for w in p["weeks"] if w["weekStart"] == ws][0]["qty"] in (30, 30.0)
          or [w for w in p["weeks"] if w["weekStart"] == ws][0]["edited"])
    check("an associate can't set targets", c.put("/api/tasks/plan", headers=H("priya"),
          json={"user_id": "8", "project_id": "diymart", "unit": "backlinks", "month": month, "qty": 1}).status_code == 403)
    r = c.post("/api/tasks/plan/template", headers=H("boss"), json={"user_id": "7", "project_id": "whatsappauto",
               "month": month, "role": "seo_lead"})
    units = {t["unit"] for t in r.json()["targets"]}
    check("role template gives a new user targets in one click", {"backlinks", "blogs"} <= units)
    sig = c.get("/api/tasks/rag", headers=H("priya")).json()["signals"]
    check("Priya gets day / week / month signals", set(sig) == {"day", "week", "month"}
          and all(s["signal"] in ("green", "amber", "red", "none") for s in sig.values()))
    team = c.get("/api/tasks/rag/team", headers=H("boss")).json()["rows"]
    check("admin sees the team grid", any(r["name"] == "Priya Sharma" for r in team))
    check("associates can't open the team grid", c.get("/api/tasks/rag/team", headers=H("priya")).status_code == 403)

    print("\n--- weekly idea (7.6) ---")
    monday = real_now.date() - timedelta(days=real_now.weekday())
    saturday = datetime.combine(monday + timedelta(days=5), datetime.min.time()).replace(hour=10)
    tm.now_ist = lambda: saturday
    items = c.get("/api/tasks/items", headers=H("priya")).json()["tasks"]
    idea_t = [t for t in items if t["kind"] == "weekly_idea"]
    check("each associate gets a weekly idea task due Friday", len(idea_t) == 1 and idea_t[0]["due_at"].endswith("18:00"))
    check("no idea by Friday → Red on Saturday", idea_t[0]["rag"] == "red")
    c.post("/api/ideas", headers=H("priya"), json={"project_id": "diymart", "title": "Gift finder quiz",
           "problem": "Shoppers can't choose", "idea": "A 5-question quiz that suggests gifts",
           "test_plan": "Run on /gifting for 2 weeks", "metric": "add-to-cart rate", "effort": "2 days"})
    items = c.get("/api/tasks/items", headers=H("priya")).json()["tasks"]
    idea_t = [t for t in items if t["kind"] == "weekly_idea"][0]
    check("submitting an idea completes it (Green)", idea_t["status"] == "approved" and idea_t["rag"] == "green")
    check("no weekly idea task for admins", not [t for t in c.get("/api/tasks/items", headers=H("boss")).json()["tasks"]
                                              if t["kind"] == "weekly_idea"])
    tm.now_ist = lambda: datetime.now(tm.store.IST).replace(tzinfo=None, second=0, microsecond=0)

    print("\n--- points, tiers, bonus privacy ---")
    check("only Jai edits tiers", c.put("/api/tasks/tiers", headers=H("boss"), json={"tiers": []}).status_code == 403)
    r = c.put("/api/tasks/tiers", headers=H("jai"), json={"tiers": [
        {"name": "Bronze", "min_points": 30, "bonus_note": "₹1,000"},
        {"name": "Silver", "min_points": 100, "bonus_note": "₹2,500"},
        {"name": "Gold", "min_points": 300, "bonus_note": "₹5,000"}]})
    check("Jai sets tiers with bonus notes", r.status_code == 200)
    m = c.get("/api/tasks/mirror", headers=H("akash")).json()
    # 34.38 (task) + 3 × 2 (social log at q3: 2 marks) … read the ledger rather than guess
    total = round(sum(x["points"] for x in m["ledger"]), 1)
    check("Mirror points = the ledger total", m["points"] == total)
    check("task approval (34.38) and the approved log (2) are in the ledger",
          {x["reason"] for x in m["ledger"]} >= {"task", "work"})
    check("Bronze reached, next tier is Silver with the right gap",
          m["tier"]["name"] == "Bronze" and m["nextTier"]["name"] == "Silver"
          and m["nextTier"]["gap"] == round(100 - m["points"], 1))
    check("Akash sees his own bonus note", m["tier"].get("bonus_note") == "₹1,000")
    check("“scope to earn more” lists concrete ways", any("Silver" in w for w in m["ways"]))
    other = c.get("/api/tasks/mirror?user_id=7", headers=H("priya")).json()
    check("Priya asking for Akash's mirror gets her own", other["userId"] == "8")
    tl = c.get("/api/tasks/tiers", headers=H("priya")).json()["tiers"]
    check("tier list hides bonus notes from associates", all("bonus_note" not in t for t in tl))
    check("admins see bonus notes", all("bonus_note" in t for t in c.get("/api/tasks/tiers", headers=H("boss")).json()["tiers"]))
    pm = c.get("/api/tasks/mirror", headers=H("priya")).json()
    check("Priya got +5 for submitting an idea", any(x["reason"] == "idea_submitted" for x in pm["ledger"]))
    rw = c.get(f"/api/tasks/rewards?month={month}", headers=H("boss")).json()
    check("monthly rewards list tiers per person", any(r["name"] == "Akash Yadav" and r["tier"] == "Bronze" for r in rw["rows"]))
    check("admin can't approve the payout sheet", c.post("/api/tasks/rewards/approve", headers=H("boss"),
          json={"month": month}).status_code == 403)
    ap = c.post("/api/tasks/rewards/approve", headers=H("jai"), json={"month": month}).json()
    check("Jai approves the month", all(r["approved"] for r in ap["rows"]))
    csv = c.get(f"/api/tasks/rewards.csv?month={month}", headers=H("jai"))
    check("payout CSV downloads", csv.status_code == 200 and "Akash Yadav" in csv.text)

    print("\n--- recurrence, load warning ---")
    r = task(title="Weekly GBP update", description="Post one GBP update every week", recurrence="weekly",
             unit="GBP posts", target_qty=1, start_at=F(real_now - timedelta(days=9)),
             due_at=F(real_now - timedelta(days=8)))
    rid = r.json()["task"]["id"]
    items = c.get("/api/tasks/items", headers=H("akash")).json()["tasks"]
    series = [t for t in items if t["series_id"] == rid]
    check("a missed weekly task gets one next copy (no pile of overdue copies)",
          len(series) == 2 and any(t["due_at"] > F(real_now) for t in series))
    r = task(title="Big audit week", description="Full technical audit of WA Auto", effort_hours=45,
             unit="audits", target_qty=1)
    check("over 40 h in a week → warning (still saves)", r.status_code == 201 and r.json()["warnings"])
    mid = r.json()["task"]["id"]
    r = c.post(f"/api/tasks/items/{mid}/progress", headers=H("akash"), json={"qty": 1, "proof_url": "https://docs.example/audit"})
    check("manual unit: assignee logs progress with a proof link", r.json()["task"]["progress"] == 1)
    check("same proof twice is refused", c.post(f"/api/tasks/items/{mid}/progress", headers=H("akash"),
          json={"qty": 1, "proof_url": "https://docs.example/audit"}).status_code == 409)
    c.post(f"/api/tasks/items/{mid}/comments", headers=H("akash"), json={"text": "Started with the crawl"})
    c.post(f"/api/tasks/items/{mid}/checklist", headers=H("boss"), json={"text": "Robots.txt"})
    d = c.get(f"/api/tasks/items/{mid}", headers=H("akash")).json()["task"]
    check("comments and checklist items", d["comments"] and d["checklist"])
    check("viewers see only their own tasks", c.get("/api/tasks/items", headers=H("intern")).json()["tasks"] == [])

    print(f"\nAll {PASS} task-manager checks passed.")


if __name__ == "__main__":
    main()
