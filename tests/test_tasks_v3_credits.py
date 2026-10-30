"""Tasks v3 hour credits and Big Ideas (Jai, 30 Oct 2026).

  * Thinking counts up to 60 min a day; a day counts up to 9 h toward credits
  * extra hours make up short days; owed = short beyond the allowance (everyone, or per person)
  * a dependency stop / Waiting tap with nothing started within 60 s debits the whole idle gap
  * Big Ideas: open board, repeat not counted, 6 counted in a month = nominee, Jai assigns
    (a task lands on that person's desk) and picks Employee of the Month once

Run:  PYTHONPATH="api;." python tests/test_tasks_v3_credits.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv3c-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v3_credits:hook",
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


def at(h, m=0, day=26, s=0):  # Monday 26 Oct 2026, IST
    return datetime(2026, 10, day, h, m, s, tzinfo=IST)


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.daily_tracker").register(app)
    wt = importlib.import_module("app.daily_tracker.worktime")
    bi = importlib.import_module("app.daily_tracker.bigideas")
    service = importlib.import_module("app.daily_tracker.service")
    store = importlib.import_module("app.daily_tracker.store")
    c = TestClient(app)
    for u in USERS.values():
        service.status(u)
    J, A, P = USERS["jai"], USERS["akash"], USERS["priya"]
    cat = store.one("SELECT id FROM task_categories WHERE name='Calling'")["id"]

    def task(user, title, day):
        return wt.create_task(user, {"title": title, "category_id": cat, "details": {"reason": "client"}},
                              at(8, day=day))[1]["task"]["id"]

    print("\n--- Mon 26: 4 h work + 2 h thinking (only 1 h counts) ---")
    wt.start_day(A, at(9))
    t1 = task(A, "Call clients", 26)
    wt.start(A, t1, at(9))
    wt.take_break(A, {"type": "thinking"}, at(13))
    s = wt.end_day(A, at(15))[1]
    check("thinking is capped at 60 min a day", s["work"]["provenMinutes"] == 300 and s["settings"]["thinkingCap"] == 60)

    print("\n--- Tue 27: 10 h, all of it counts (no daily cap) ---")
    wt.start_day(A, at(9, day=27))
    wt.start(A, t1, at(9, day=27))
    s = wt.end_day(A, at(19, day=27))[1]
    check("all 10 h count", s["work"]["provenMinutes"] == 600)

    print("\n--- Wed 28: a quick switch after a stop is free, 30 min of Waiting is not ---")
    wt.start_day(A, at(9, day=28))
    t2 = task(A, "Call new leads", 28)
    wt.start(A, t1, at(9, day=28))
    wt.block(A, t1, {"depends_on_name": "Client", "reason": "Credentials expired"}, at(10, day=28))
    wt.start(A, t2, at(10, 0, day=28, s=30))
    wt.take_break(A, {"type": "waiting"}, at(12, day=28))
    wt.take_break(A, {"type": "waiting"}, at(12, 30, day=28))
    wt.end_day(A, at(16, 0, day=28, s=30))
    check("idle: 30 s after the stop is free, the 30 min wait is debited",
          wt.idle_minutes("7", "2026-10-28", "2026-10-29") == 30)

    print("\n--- Thu 29: a short day (1 h) ---")
    wt.start_day(A, at(9, day=29))
    wt.start(A, t2, at(9, day=29))
    wt.end_day(A, at(10, day=29))

    print("\n--- the work month (26 Oct - 25 Nov) on Fri 30 ---")
    check("the work month runs 26th to 25th", wt.cycle_of(wt._date(2026, 10, 26)) == "2026-11"
          and wt.cycle_of(wt._date(2026, 10, 25)) == "2026-10"
          and wt.cycle_bounds("2026-11") == (wt._date(2026, 10, 26), wt._date(2026, 11, 25))
          and wt.cycle_bounds("2027-01") == (wt._date(2026, 12, 26), wt._date(2027, 1, 25)))
    F = at(9, day=30)
    m = wt.month_credit("7", "2026-11", F)
    check("worked 5 + 10 + 6.5 + 1 h against 4 x 7 h", m["workedMinutes"] == 1350 and m["targetMinutes"] == 1680
          and m["from"] == "2026-10-26" and m["to"] == "2026-11-25")
    check("5.5 h short and 30 min idle = owes 6 h", m["balanceMinutes"] == -360 and m["owedMinutes"] == 360)
    check("rings closed: 1 of 4 days", m["ringsClosed"] == 1 and m["ringDays"] == 4)
    check("days before the work month don't count", wt.month_credit("7", "2026-10", F)["targetMinutes"] == 0)
    check("only Jai sets the allowance", wt.set_allowance(A, {"hours": 5}, F)[0] == 403)
    check("the allowance is 0 to 200 h", wt.set_allowance(J, {"hours": -1}, F)[0] == 400)
    wt.set_allowance(J, {"user_id": "*", "hours": 0.5}, F)
    check("everyone may be 30 min short: owes 5.5 h", wt.month_credit("7", "2026-11", F)["owedMinutes"] == 330)
    wt.set_allowance(J, {"user_id": "7", "hours": 2}, F)
    check("Akash's own 2 h beats everyone's: owes 4 h",
          wt.month_credit("7", "2026-11", F)["owedMinutes"] == 240 and wt.allowance_hours("8") == 0.5)
    s = wt.state(J, F)[1]
    check("Jai sees everyone's credits", {p["user_id"]: p["allowanceHours"] for p in s["teamCredits"]}["7"] == 2
          and s["allowanceAll"] == 0.5)
    check("a person never sees the team", wt.state(A, F)[1]["teamCredits"] == []
          and wt.state(A, F)[1]["credit"]["owedMinutes"] == 240)
    check("days before someone's first day don't count", wt.month_credit("8", "2026-11", F)["targetMinutes"] == 0)

    print("\n--- Big Ideas ---")
    idea = {"channel": "ChatGPT", "idea": "Publish answer pages that ChatGPT quotes for agentic automation questions."}
    check("POST /api/tasks/v2/ideas answers", c.post("/api/tasks/v2/ideas", headers={"x-user": "priya"},
                                                     json={"title": "x"}).status_code == 400)
    check("needs a known channel", bi.submit(P, {**idea, "title": "Answer pages", "channel": "MySpace"})[0] == 400)
    for n in range(6):
        code, b = bi.submit(P, {**idea, "title": f"Priya idea {n + 1}"}, at(10, day=29))
    me = {p["user_id"]: p for p in b["people"]}
    check("6 counted ideas in a month = nominee", code == 200 and me["8"]["counted"] == 6 and me["8"]["nominated"])
    first = min(i["id"] for i in b["ideas"] if i["user_id"] == "8")
    check("only Jai decides", bi.decide(P, first, {"status": "worked"})[0] == 403)
    b = bi.decide(J, first, {"status": "repeat", "note": "Jai gave this in September"}, at(11, day=29))[1]
    check("a repeat doesn't count: 5, not a nominee", {p["user_id"]: p for p in b["people"]}["8"]["counted"] == 5
          and not {p["user_id"]: p for p in b["people"]}["8"]["nominated"])
    bi.submit(P, {**idea, "title": "Priya idea 7"}, at(12, day=29))
    second = first + 1
    check("assigning needs a person and a project", bi.decide(J, second, {"status": "assigned"})[0] == 400)
    b = bi.decide(J, second, {"status": "assigned", "assign_to": "7", "project": "agenticaiautomation.co"},
                  at(12, day=29))[1]
    i = next(x for x in b["ideas"] if x["id"] == second)
    t = store.one("SELECT * FROM work_tasks WHERE id=?", (i["task_id"],))
    check("assigned: a task lands on Akash's desk", t["assigned_to"] == "7" and t["title"].startswith("Apply idea:")
          and t["domain"] == "agenticaiautomation.co" and i["assignedName"] == "Akash Yadav")
    bi.decide(J, second, {"status": "worked", "note": "cited by ChatGPT"}, at(13, day=29))
    check("marking it worked keeps the assignment", store.one("SELECT assigned_to, task_id FROM big_ideas WHERE id=?",
                                                               (second,))["task_id"] == t["id"])
    bi.submit(A, {**idea, "title": "Akash idea"}, at(12, day=29))
    check("Akash (1 idea) isn't a nominee", bi.pick_employee_of_month(J, {"user_id": "7"}, at(14, day=29))[0] == 400)
    code, b = bi.pick_employee_of_month(J, {"user_id": "8"}, at(14, day=29))
    check("Jai picks Priya", code == 200 and b["employeeOfMonth"]["name"] == "Priya Sharma")
    check("once a month", bi.pick_employee_of_month(J, {"user_id": "8"}, at(15, day=29))[0] == 409)

    print("\n--- switch off ---")
    wt.settings.TASKS_V3 = False
    check("v3 off: ideas answer 404", bi.board(A)[0] == 404 and wt.state(A, at(9, day=29))[1]["credit"] is None)
    print(f"\nAll {PASS} credit and idea checks passed.")


if __name__ == "__main__":
    main()
