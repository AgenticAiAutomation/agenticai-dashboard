"""Tasks v3 Step 6: points, streaks, levels, badges, weekly leaderboard, Jai's accept queue,
and the month bar (complete only with the month's idea).

Run:  PYTHONPATH="api;." python tests/test_tasks_v3_game.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv3g-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v3_game:hook",
    "DAILY_TRACKER_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"),
    "FEATURE_TASKS_V2": "1", "FEATURE_TASKS_V3": "1",
})

USERS = {
    "jai":   {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
    "akash": {"id": 7, "name": "Akash Yadav", "email": "akash0710yadav@gmail.com", "role": "seo_lead"},
    "priya": {"id": 8, "name": "Priya Sharma", "email": "priya@example.com", "role": "seo_lead"},
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


def at(h, m=0, day=26, month=10, s=0):  # Monday 26 Oct 2026, IST
    return datetime(2026, month, day, h, m, s, tzinfo=IST)


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.daily_tracker").register(app)
    wt = importlib.import_module("app.daily_tracker.worktime")
    game = importlib.import_module("app.daily_tracker.game")
    bi = importlib.import_module("app.daily_tracker.bigideas")
    service = importlib.import_module("app.daily_tracker.service")
    store = importlib.import_module("app.daily_tracker.store")
    c = TestClient(app)
    for u in USERS.values():
        service.status(u)
    J, A, P = USERS["jai"], USERS["akash"], USERS["priya"]
    cat = store.one("SELECT id FROM task_categories WHERE name='Calling'")["id"]

    def give(title, minutes, cx, day=26, month=10, who="7"):
        code, out = wt.create_task(J, {"title": title, "category_id": cat, "details": {"reason": "client"},
                                       "estimate_min": minutes, "complexity": cx, "assign_to": who}, at(8, day=day, month=month))
        return out["task"]["id"]

    def full_day(day, month=10, start=9, hours=7, who=A):
        wt.start_day(who, at(start, day=day, month=month))
        t = give(f"Work {month}/{day}", 60, "Easy", day, month, str(who["id"]))
        wt.start(who, t, at(start, day=day, month=month))
        wt.end_day(who, at(start + hours, day=day, month=month))
        return t

    print("\n--- points on offer ---")
    check("complexity is Easy, Medium or Hard", wt.create_task(J, {"title": "Bad", "category_id": cat,
          "details": {"reason": "x"}, "complexity": "Insane"}, at(8))[0] == 400)
    t1 = give("Call the dental lead", 60, "Hard")
    check("1 h Hard = 20 x 2 = 40 points", game.task_points(wt._task(t1)) == 40)
    check("15m Easy = 5, 30m Medium = 15, 3h Easy = 60",
          [game.task_points({"estimate_min": m, "details": {"complexity": x}}) for m, x in
           ((15, "Easy"), (30, "Medium"), (180, "Easy"))] == [5, 15, 60])

    print("\n--- Done waits for Jai; accepted = earned ---")
    wt.start_day(A, at(9))
    wt.start(A, t1, at(9))
    wt.complete(A, t1, {}, at(10))
    s = wt.state(A, at(10))[1]
    check("after Done the points are pending", s["game"]["pending"] == 40 and s["game"]["points"] == 0)
    check("Jai's queue shows it with its points", [(r["id"], r["points"]) for r in wt.state(J, at(10))[1]["toReview"]] == [(t1, 40)])
    check("only Jai accepts", game.review(A, t1, {"accept": True}, at(10))[0] == 403)
    check("sending back needs a note", game.review(J, t1, {"accept": False}, at(10))[0] == 400)
    game.review(J, t1, {"accept": False, "note": "Log the call outcome"}, at(10, 5))
    check("sent back: the task waits as paused, no points", wt._task(t1)["status"] == "paused"
          and wt.state(A, at(10, 5))[1]["game"]["pending"] == 0)
    wt.start(A, t1, at(10, 10))
    wt.complete(A, t1, {}, at(10, 20))
    s = game.review(J, t1, {"accept": True}, at(10, 30))[1]
    check("accepted: 40 points earned, once", wt._task(t1)["status"] == "accepted"
          and game.summary("7", at(10, 30))["points"] == 40 and game.review(J, t1, {"accept": True}, at(10, 31))[0] == 404)
    t2 = give("Follow up", 60, "Easy")
    wt.start(A, t2, at(10, 30))
    wt.end_day(A, at(16, 30))

    print("\n--- streaks and day badges ---")
    for d in (27, 28, 29, 30, 31):
        full_day(d)
    s = game.summary("7", at(8, day=1, month=11))
    check("Sunday 1 Nov has no target and doesn't break it", s["streak"] == 6)
    full_day(2, 11)
    s = game.summary("7", at(20, day=2, month=11))
    check("today counts once its hours are met: 7 in a row", s["streak"] == 7)
    b = {x["code"]: x["count"] for x in s["badges"]}
    check("Ring Closer per day, Early Bird per on-time start, 5-day Streak once", b["ring_closer"] == 7
          and b["early_bird"] == 7 and b["streak_5d"] == 1 and "streak_20d" not in b)
    wt.start_day(A, at(9, day=3, month=11))
    wt.end_day(A, at(10, day=3, month=11))
    check("a short day breaks the streak the next morning", game.summary("7", at(9, day=4, month=11))["streak"] == 0)

    print("\n--- Hard Mode and Blocker Buster ---")
    wt.start_day(P, at(9, day=4, month=11))
    for n in range(5):
        t = give(f"Hard {n}", 15, "Hard", 4, 11, "8")
        wt.start(P, t, at(9, n * 10, day=4, month=11))
        wt.complete(P, t, {}, at(9, n * 10 + 5, day=4, month=11))
        game.review(J, t, {"accept": True}, at(12, day=4, month=11))
    tb, tn = give("Blocked one", 30, "Easy", 4, 11, "8"), give("Next one", 30, "Easy", 4, 11, "8")
    wt.start(P, tb, at(13, day=4, month=11))
    wt.block(P, tb, {"depends_on_name": "Client", "reason": "Document required"}, at(13, 10, day=4, month=11))
    wt.start(P, tn, at(13, 11, day=4, month=11))
    s = game.summary("8", at(14, day=4, month=11))
    b = {x["code"] for x in s["badges"]}
    check("5 Hard tasks accepted in a week = Hard Mode; 5 x 10 points", "hard_mode" in b and s["points"] == 50)
    check("next task within 2 min of a block = Blocker Buster", "blocker_buster" in b)

    print("\n--- ideas and Wins earn points and badges ---")
    idea = {"channel": "ChatGPT", "idea": "Publish answer pages that ChatGPT quotes for agentic automation questions."}
    s = wt.state(A, at(15, day=4, month=11))[1]
    check("month bar: no idea yet, so it can't complete", s["monthGoal"]["ideaGiven"] is False
          and s["monthGoal"]["month"] == "2026-11" and s["monthGoal"]["workedMinutes"] > 0)
    b = bi.submit(A, {**idea, "title": "Answer pages"}, at(15, day=4, month=11))[1]
    iid = b["ideas"][0]["id"]
    bi.decide(J, iid, {"status": "worked", "note": "quoted"}, at(15, day=4, month=11))
    bi.submit_win(A, {"what": "Got the clinic page to Google's top 3", "for_whom": "Smile Dental", "result": "Top 3"},
                  at(15, day=4, month=11))
    wid = store.one("SELECT id FROM achievements")["id"]
    bi.decide_win(J, wid, {"decision": "approved"}, at(15, day=4, month=11))
    s = wt.state(A, at(16, day=4, month=11))[1]
    b = {x["code"] for x in s["game"]["badges"]}
    check("idea given: the month bar can complete", s["monthGoal"]["ideaGiven"] is True)
    check("worked idea +50, approved Win +25", s["game"]["points"] == 40 + 50 + 25)
    check("Idea Maker and Achiever badges", {"idea_maker", "achiever"} <= b)
    check("level from points (Starter below 200)", s["game"]["level"] == "Starter" and s["game"]["nextLevel"]["at"] == 200)

    print("\n--- weekly leaderboard ---")
    lb = wt.state(A, at(16, day=4, month=11))[1]["leaderboard"]
    check("this week only, points and target days, never hours",
          [(r["name"], r["points"], r["rings"]) for r in lb] == [("Akash Yadav", 75, 1), ("Priya Sharma", 50, 0)]
          and all("minutes" not in k.lower() and "hours" not in k.lower() for r in lb for k in r))
    check("POST /api/tasks/v2/tasks/{id}/review answers",
          c.post(f"/api/tasks/v2/tasks/{t2}/review", headers={"x-user": "priya"}, json={"accept": True}).status_code == 403)
    print(f"\nAll {PASS} game checks passed.")


if __name__ == "__main__":
    main()
