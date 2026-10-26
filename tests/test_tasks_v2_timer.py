"""Tasks v2, Step 2: the task timer, 15-minute proof and road blockers.

  * a task can't be added without its category's fields (website, page + updates, reason, ...)
  * one running task per person; starting another pauses the first; a refresh shows the server's timer
  * overlapping time is never counted twice; a 15-minute slot counts only once it has proof
  * yesterday is locked; a timer forgotten overnight blocks everything until its end time is set
  * road blocker: the watch stops, New website development waits for Jai, the next task is suggested
    (own tasks by priority then due date, then the Pool; never the blocked one)
  * pool pick, complete needs proof, viewers read only, flag off = 404

Run:  PYTHONPATH="api;." python tests/test_tasks_v2_timer.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv2t-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v2_timer:hook",
    "DAILY_TRACKER_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"),
    "FEATURE_TASKS_V2": "1",
})

USERS = {
    "jai":    {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
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


IST = timezone(timedelta(hours=5, minutes=30))


def at(h, m=0, day=26):  # Monday 26 Oct 2026, IST
    return datetime(2026, 10, day, h, m, tzinfo=IST)


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.daily_tracker").register(app)
    wt = importlib.import_module("app.daily_tracker.worktime")
    service = importlib.import_module("app.daily_tracker.service")
    store = importlib.import_module("app.daily_tracker.store")
    c = TestClient(app)
    for u in USERS.values():
        service.status(u)
    J, A, P, I = USERS["jai"], USERS["akash"], USERS["priya"], USERS["intern"]
    cat = {r["name"]: r["id"] for r in store.rows("SELECT id, name FROM task_categories")}

    print("\n--- routes and flag ---")
    st = c.get("/api/tasks/status", headers={"x-user": "akash"}).json()
    check("status reports tasksV2", st.get("tasksV2") is True)
    check("GET /api/tasks/v2/state answers", c.get("/api/tasks/v2/state", headers={"x-user": "akash"}).status_code == 200)

    def new(user, name, details, now=at(9), **kw):
        return wt.create_task(user, {"title": kw.pop("title", f"{name} task"), "category_id": cat[name],
                                     "details": details, **kw}, now)

    print("\n--- categories demand their fields ---")
    check("Article writing without the website name is refused",
          new(A, "Article writing", {})[0] == 400)
    check("Content writing must say Social media or Backlinks",
          new(A, "Content writing", {"purpose": "Blog"})[0] == 400)
    check("Website development needs page AND updates",
          new(A, "Website development", {"page": "/pricing"})[0] == 400)
    check("Calling needs a reason", new(A, "Calling", {"reason": " "})[0] == 400)
    code, out = new(A, "Article writing", {"website": "agenticaiautomation.co"}, title="UiPath for CA firms")
    check("Article writing with the website saves as Akash's own task",
          code == 201 and out["task"]["assigned_to"] == "7" and out["task"]["status"] == "todo")
    ta = out["task"]["id"]
    code, out = new(A, "New website development", {"website": "newclient.in"}, priority="P1")
    check("New website development is due 3 working days later (Mon -> Thu)",
          code == 201 and out["task"]["due_date"] == "2026-10-29")
    tb = out["task"]["id"]
    check("an associate can't post to the Pool (it stays theirs)",
          new(A, "Meeting", {"reason": "weekly"}, assign_to="pool")[1]["task"]["assigned_to"] == "7")
    code, out = new(J, "Content writing", {"purpose": "Backlinks"}, assign_to="pool", title="5 guest posts")
    check("Jai posts a task to the Pool", code == 201 and out["task"]["pool"] and out["task"]["status"] == "pool")
    tp = out["task"]["id"]
    check("a viewer can't add tasks", new(I, "Calling", {"reason": "x"})[0] == 403)

    print("\n--- one running task; switch pauses; refresh keeps the timer ---")
    wt.start(A, ta, at(10))
    code, s = wt.start(A, ta, at(10, 5))
    check("starting the same task again changes nothing",
          store.one("SELECT COUNT(*) c FROM work_intervals WHERE user_id='7'")["c"] == 1)
    code, s = wt.start(A, tb, at(10, 20))
    check("starting another task pauses the first",
          s["running"]["task"]["id"] == tb
          and store.one("SELECT status FROM work_tasks WHERE id=?", (ta,))["status"] == "paused")
    check("the pause is in the event trail",
          store.one("SELECT COUNT(*) c FROM task_events WHERE task_id=? AND event_type='auto_pause'", (ta,))["c"] == 1)
    code, s = wt.state(A, at(10, 30))
    check("a refresh shows the running timer from the server (started 10:20)",
          s["running"]["interval"]["start_ts"] == "2026-10-26T04:50:00+00:00" and not s["running"]["stale"])
    check("worked 30 min, none proven yet, 2 slots need proof",
          s["work"]["workedMinutes"] == 30 and s["work"]["provenMinutes"] == 0
          and [x["slot"] for x in s["work"]["needProof"]] == ["2026-10-26T10:00", "2026-10-26T10:15"])
    check("left today = 7 h (nothing proven)", s["work"]["leftMinutes"] == 420)

    print("\n--- 15-minute proof ---")
    def proof(slot, now=at(10, 30), **kw):
        return wt.add_proof(A, {"slot": slot, **kw}, now)
    check("proof needs a note", proof("2026-10-26T10:00", url="https://agenticaiautomation.co/blog/uipath")[0] == 400)
    check("proof needs a link, image name or logo name", proof("2026-10-26T10:00", note="wrote intro")[0] == 400)
    code, s = proof("2026-10-26T10:00", url="https://agenticaiautomation.co/blog/uipath-for-ca", note="wrote intro")
    check("proof with a link counts those 15 minutes", code == 200 and s["work"]["provenMinutes"] == 15)
    row = store.one("SELECT * FROM work_slots WHERE slot_start='2026-10-26T10:00'")
    check("domain and URL slug are taken from the link",
          row["domain"] == "agenticaiautomation.co" and row["url_slug"] == "blog/uipath-for-ca" and row["task_id"] == ta)
    check("the same 15 minutes can't get proof twice",
          proof("2026-10-26T10:00", image_name="hero.png", note="x")[0] == 409)
    check("no proof for 15 minutes with no timer time", proof("2026-10-26T09:00", logo_name="l.svg", note="x")[0] == 400)
    check("yesterday is locked", proof("2026-10-25T10:00", logo_name="l.svg", note="x")[0] == 409)
    code, s = proof("2026-10-26T10:15", image_name="newclient-hero.webp", note="home page hero")
    check("an image name is proof too", s["work"]["provenMinutes"] == 30)
    store.write("INSERT INTO work_intervals(user_id, task_id, type, start_ts, end_ts, created_at) "
                "VALUES ('7', ?, 'work', '2026-10-26T04:30:00+00:00', '2026-10-26T04:40:00+00:00', 'x')", (ta,))
    code, s = wt.state(A, at(10, 30))
    check("an overlapping interval is never counted twice", s["work"]["workedMinutes"] == 30)

    print("\n--- road blocker ---")
    tc = new(A, "Website development", {"page": "/pricing", "updates": "new plans"}, priority="P1",
             due_date="2026-10-28")[1]["task"]["id"]
    td = new(A, "Calling", {"reason": "renewal"}, priority="P2", due_date="2026-10-27")[1]["task"]["id"]
    check("a block needs who and why", wt.block(A, tb, {"depends_on_name": "Client Ravi"}, at(10, 40))[0] == 400)
    code, s = wt.block(A, tb, {"depends_on_name": "Client Ravi", "reason": "logo files not sent"}, at(10, 40))
    check("the watch stops the moment the blocker is named", code == 200 and s["running"] is None)
    check("New website development: the hold waits for Jai",
          s["needsApproval"] and store.one("SELECT status FROM task_holds WHERE task_id=?", (tb,))["status"] == "pending")
    order = [t["id"] for t in s["suggestions"]]
    meeting = [t["id"] for t in s["suggestions"] if t["category"] == "Meeting"]
    check("next task suggested: P1 first, then P2 by due date, then the rest, then the Pool; never the blocked one",
          order[:3] == [tc, td, ta] and tb not in order and order[-1] == tp and meeting)
    code, s = wt.start(A, tc, at(10, 41))
    check("one click starts the suggested task", s["running"]["task"]["id"] == tc)
    check("only Jai decides a hold", wt.decide_hold(A, 1, {"approve": True}, at(11))[0] == 403)
    code, s = wt.state(J, at(11))
    check("Jai sees the hold waiting", [h["task_id"] for h in s["approve"]] == [tb])
    wt.decide_hold(J, s["approve"][0]["id"], {"approve": True, "note": "ok, client delay"}, at(11))
    check("approved, and it can't be decided again",
          store.one("SELECT status FROM task_holds WHERE task_id=?", (tb,))["status"] == "approved"
          and wt.decide_hold(J, s["approve"][0]["id"], {"approve": False}, at(11))[0] == 404)
    th = new(A, "Calling", {"reason": "follow up quote"})[1]["task"]["id"]
    code, s = wt.block(A, th, {"depends_on_user_id": "8", "reason": "needs Priya's price list"}, at(11, 5))
    hold = store.one("SELECT * FROM task_holds WHERE task_id=?", (th,))
    check("a block on a teammate records them; Calling doesn't need Jai",
          hold["depends_on_name"] == "Priya Sharma" and hold["status"] == "noted" and not s["needsApproval"])
    check("blocking another task leaves the running one running", s["running"]["task"]["id"] == tc)
    code, s = wt.unblock(A, tb, at(12))
    check("unblock: the task is workable again and the hold has ended",
          store.one("SELECT status FROM work_tasks WHERE id=?", (tb,))["status"] == "paused"
          and store.one("SELECT end_ts FROM task_holds WHERE task_id=?", (tb,))["end_ts"])

    print("\n--- pool, complete ---")
    code, s = wt.start(A, tp, at(12, 5))
    t = store.one("SELECT * FROM work_tasks WHERE id=?", (tp,))
    check("starting a Pool task picks it", t["assigned_to"] == "7" and t["picked_by"] == "7" and not t["pool"])
    check("someone else can't then start it", wt.start(P, tp, at(12, 6))[0] == 403)
    check("complete needs a proof link", wt.complete(A, tp, {}, at(13))[0] == 400)
    code, s = wt.complete(A, tp, {"evidence_url": "https://docs.google.com/x"}, at(13))
    check("complete: submitted, timer stopped",
          s["running"] is None and store.one("SELECT status FROM work_tasks WHERE id=?", (tp,))["status"] == "submitted")

    print("\n--- forgotten timer ---")
    wt.start(A, ta, at(17))
    code, s = wt.state(A, at(10, day=27))
    check("next morning: the open session from yesterday is flagged", s["running"]["stale"])
    check("nothing starts until its end is set", wt.start(A, tc, at(10, day=27))[0] == 409)
    check("pause can't invent the end either", wt.pause(A, at(10, day=27))[0] == 409)
    check("the end must be on that day",
          wt.end_session(A, {"end": "2026-10-27T09:00"}, at(10, day=27))[0] == 400)
    code, s = wt.end_session(A, {"end": "2026-10-26T18:30"}, at(10, day=27))
    check("setting 18:30 closes it, marked as set by the person",
          s["running"] is None
          and store.one("SELECT COUNT(*) c FROM task_events WHERE event_type='manual_end'")["c"] == 1)
    check("then work starts normally", wt.start(A, tc, at(10, 1, day=27))[1]["running"]["task"]["id"] == tc)

    print("\n--- switch off ---")
    wt.settings.TASKS_V2 = False
    check("flag off: 404", wt.state(A)[0] == 404)
    print(f"\nAll {PASS} timer checks passed.")


if __name__ == "__main__":
    main()
