"""Tasks v3, Step 1: "Start my day" (login = clock-in).

  * Start my day records the server time; after the late time (default 10:30) the day is "late"
  * pressing it twice changes nothing; a task can't start before the day starts or after it ends
  * End my day stops the running task
  * a day left open blocks the next one until the person says when they stopped (never guessed);
    a timer left running that day stops at the same time
  * work_days rows are never deleted, and a day is ended once
  * flag off: the day routes answer 404 and tasks start as in v2

Run:  PYTHONPATH="api;." python tests/test_tasks_v3_day.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv3d-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v3_day:hook",
    "DAILY_TRACKER_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"),
    "FEATURE_TASKS_V2": "1", "FEATURE_TASKS_V3": "1",
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
    A, P, I = USERS["akash"], USERS["priya"], USERS["intern"]
    cat = store.one("SELECT id FROM task_categories WHERE name='Calling'")["id"]

    def task(user, title):
        return wt.create_task(user, {"title": title, "category_id": cat, "details": {"reason": "client"}}, at(9))[1]["task"]["id"]

    print("\n--- routes and flag ---")
    check("status reports tasksV3", c.get("/api/tasks/status", headers={"x-user": "akash"}).json().get("tasksV3") is True)
    check("POST /api/tasks/v2/day/start answers", c.post("/api/tasks/v2/day/start", headers={"x-user": "jai"}).status_code == 200)

    print("\n--- start my day ---")
    t1, t2 = task(A, "Call the dentist lead"), task(A, "Call back Mehta")
    code, s = wt.state(A, at(9, 30))
    check("before Start: no day, the flow is on", s["dayFlow"] and s["day"] is None)
    check("a task can't start before the day starts", wt.start(A, t1, at(9, 35))[1]["error"] == "day_not_started")
    code, s = wt.start_day(A, at(9, 42))
    check("Start my day records the server time, on time",
          s["day"]["start_at"] == "2026-10-26T04:12:00+00:00" and s["day"]["status"] == "on_time")
    wt.start_day(A, at(9, 50))
    check("pressing it again changes nothing",
          store.one("SELECT COUNT(*) c FROM work_days WHERE user_id='7'")["c"] == 1
          and wt.state(A, at(9, 51))[1]["day"]["start_at"] == "2026-10-26T04:12:00+00:00")
    check("the start is in the event trail",
          store.one("SELECT COUNT(*) c FROM task_events WHERE user_id='7' AND event_type='day_start'")["c"] == 1)
    check("after 10:30 the day is a late start", wt.start_day(P, at(10, 31))[1]["day"]["status"] == "late")
    check("a viewer can't start a day", wt.start_day(I, at(9))[0] == 403)

    print("\n--- end my day ---")
    check("then a task starts", wt.start(A, t1, at(10))[1]["running"]["task"]["id"] == t1)
    code, s = wt.end_day(A, at(18, 30))
    check("End my day stops the running task",
          s["running"] is None and s["day"]["end_at"] == "2026-10-26T13:00:00+00:00"
          and store.one("SELECT status FROM work_tasks WHERE id=?", (t1,))["status"] == "paused")
    check("no task starts after the day ended", wt.start(A, t2, at(18, 40))[1]["error"] == "day_ended")
    wt.end_day(A, at(19))
    check("pressing End again keeps the first time",
          wt.state(A, at(19))[1]["day"]["end_at"] == "2026-10-26T13:00:00+00:00")

    print("\n--- forgotten End my day ---")
    wt.start_day(A, at(9, day=27))
    wt.start(A, t2, at(16, day=27))
    code, s = wt.state(A, at(9, day=28))
    check("next login: yesterday is flagged as not ended", s["openDay"]["date"] == "2026-10-27" and s["day"] is None)
    check("today can't start until it is set", wt.start_day(A, at(9, day=28))[1]["error"] == "open_day")
    check("the stop time must be on that day",
          wt.set_day_end(A, {"end": "2026-10-28T08:00"}, at(9, day=28))[0] == 400)
    check("not before the day started",
          wt.set_day_end(A, {"end": "2026-10-27T08:00"}, at(9, day=28))[0] == 400)
    check("not before the timer that ran that day",
          wt.set_day_end(A, {"end": "2026-10-27T15:00"}, at(9, day=28))[0] == 400)
    code, s = wt.set_day_end(A, {"end": "2026-10-27T18:15"}, at(9, day=28))
    d = store.one("SELECT * FROM work_days WHERE user_id='7' AND date='2026-10-27'")
    check("18:15 ends the day, marked as set later", code == 200 and s["openDay"] is None
          and d["end_at"] == "2026-10-27T12:45:00+00:00" and d["end_source"] == "set_later")
    iv = store.one("SELECT * FROM work_intervals WHERE user_id='7' AND task_id=? ORDER BY id DESC", (t2,))
    check("the timer left running stops at the same time", iv["end_ts"] == "2026-10-27T12:45:00+00:00")
    check("then today starts normally", wt.start_day(A, at(9, 5, day=28))[1]["day"]["date"] == "2026-10-28")

    print("\n--- no proof in v3 (Jai, 27 Oct) ---")
    wt.start(A, t1, at(10, day=28))
    s = wt.state(A, at(10, 30, day=28))[1]
    check("timer time counts as it runs, nothing asks for proof",
          s["work"]["provenMinutes"] == s["work"]["workedMinutes"] == 30 and s["work"]["needProof"] == [])
    check("Done needs no link", wt.complete(A, t1, {}, at(10, 30, day=28))[0] == 200
          and store.one("SELECT status FROM work_tasks WHERE id=?", (t1,))["status"] == "submitted")
    check("a link given must still be a link", wt.complete(A, t2, {"evidence_url": "nope"}, at(10, 31, day=28))[0] == 400)

    print("\n--- dependency stop: reasons + Jai's daily tasks ---")
    J = USERS["jai"]
    daily = {"title": "Reply to client emails", "category_id": cat, "details": {"reason": "inbox"}}
    check("only Jai sets daily tasks", wt.create_routine(A, daily)[0] == 403)
    check("a daily task needs its category's fields",
          wt.create_routine(J, {**daily, "details": {}})[0] == 400)
    wt.create_routine(J, daily)
    wt.create_routine(J, {**daily, "title": "Priya's social posts", "user_id": "8"})
    r_all, r_priya = [r["id"] for r in store.rows("SELECT id FROM daily_routines ORDER BY id")]
    wt.start(A, t2, at(11, day=28))
    block = {"depends_on_name": "Client", "reason": "Lunch"}
    check("the reason must be one of the options", wt.block(A, t2, block, at(11, 10, day=28))[0] == 400)
    code, s = wt.block(A, t2, {**block, "reason": "Credentials expired", "detail": "WordPress login"}, at(11, 10, day=28))
    check("Credentials expired stops the watch, no proof asked", code == 200 and s["running"] is None
          and store.one("SELECT reason FROM task_holds WHERE task_id=?", (t2,))["reason"]
          == "Credentials expired: WordPress login")
    check("the answer offers everyone's daily tasks, not Priya's own", [r["id"] for r in s["routines"]] == [r_all])
    check("Akash can't jump to Priya's daily task", wt.start_routine(A, r_priya, at(11, 11, day=28))[0] == 404)
    code, s = wt.start_routine(A, r_all, at(11, 11, day=28))
    first = s["running"]["task"]
    check("one tap: the daily task becomes his and starts",
          code == 200 and first["title"] == "Reply to client emails" and first["details"]["routine_id"] == r_all)
    wt.pause(A, at(11, 30, day=28))
    check("jumping again carries on the same task, no copy",
          wt.start_routine(A, r_all, at(12, day=28))[1]["running"]["task"]["id"] == first["id"])
    wt.set_routine_active(J, r_all, {"active": False})
    check("Jai switches it off: no longer offered, kept for him",
          wt.routines("7") == [] and len(wt.state(J, at(12, day=28))[1]["routinesAll"]) == 2)

    print("\n--- guardrails ---")
    conn = store.connect()
    for sql in ("DELETE FROM work_days", "DELETE FROM daily_routines", "UPDATE work_days SET end_at='2026-10-26T14:00:00+00:00' WHERE date='2026-10-26'",
                "UPDATE work_days SET start_at='2026-10-28T03:00:00+00:00' WHERE date='2026-10-28'",
                "UPDATE work_days SET status='on_time', end_at='2026-10-26T13:00:00+00:00' WHERE user_id='8'",
                "INSERT OR REPLACE INTO work_days(user_id, date, start_at) VALUES ('7', '2026-10-26', 'x')"):
        try:
            with conn:
                conn.execute(sql)
            ok = False
        except sqlite3.DatabaseError:
            ok = True
        check(f"refused: {sql[:60]}", ok)

    print("\n--- switch off ---")
    wt.settings.TASKS_V3 = False
    check("v3 off: day routes answer 404", wt.start_day(P, at(9, day=29))[0] == 404)
    t3 = task(P, "Call v2 style")
    check("v3 off: a task starts without a day, as in v2", wt.start(P, t3, at(9, day=29))[0] == 200)
    print(f"\nAll {PASS} day checks passed.")


if __name__ == "__main__":
    main()
