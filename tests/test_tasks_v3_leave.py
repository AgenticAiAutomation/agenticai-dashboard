"""Tasks v3 leave: 2 full days + 2 short leaves (2.5 h) per work month, per person if Jai says so;
leave excuses that day's hours; unused leave carries to the next work month as hours.

Run:  PYTHONPATH="api;." python tests/test_tasks_v3_leave.py
"""
import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv3l-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v3_leave:hook",
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


def at(h, m=0, day=26, month=10):  # Monday 26 Oct 2026, IST
    return datetime(2026, month, day, h, m, tzinfo=IST)


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.daily_tracker").register(app)
    wt = importlib.import_module("app.daily_tracker.worktime")
    lv = importlib.import_module("app.daily_tracker.leave")
    service = importlib.import_module("app.daily_tracker.service")
    store = importlib.import_module("app.daily_tracker.store")
    c = TestClient(app)
    for u in USERS.values():
        service.status(u)
    J, A, P = USERS["jai"], USERS["akash"], USERS["priya"]
    N = at(10)

    print("\n--- allowance ---")
    check("default: 2 days + 2 short leaves of 2.5 h", lv.policy("7") == {"days": 2, "short_count": 2, "short_hours": 2.5})
    wt.start_day(A, at(9))
    full = lambda d, now=N: lv.take(A, {"type": "full", "date": d}, now)  # noqa: E731
    short = lambda d, h, now=N: lv.take(A, {"type": "short", "date": d, "hours": h}, now)  # noqa: E731
    check("POST /api/tasks/v2/leave answers", c.post("/api/tasks/v2/leave", headers={"x-user": "jai"},
                                                     json={"type": "nap"}).status_code == 400)
    check("not on a past day", full("2026-10-25")[0] == 400)
    check("not on a day with no hours (Sunday)", full("2026-11-01")[0] == 400)
    check("a full day", full("2026-10-28")[0] == 200)
    check("one leave a day", full("2026-10-28")[0] == 409)
    check("a second full day", full("2026-10-30")[0] == 200)
    check("no third full day this work month", full("2026-11-02")[0] == 400)
    check("a short leave is up to 2.5 h", short("2026-10-29", 3)[0] == 400)
    check("a short leave of 2.5 h", short("2026-10-29", 2.5)[0] == 200)
    check("a second short leave of 1 h", short("2026-10-31", 1)[0] == 200)
    check("no third short leave", short("2026-11-03", 1)[0] == 400)
    check("the next work month is a fresh allowance", full("2026-11-27")[0] == 200)

    print("\n--- leave excuses the day's hours ---")
    check("full day: 0 h to work; short: 7 - 2.5 = 4.5 h",
          wt.user_target("7", "2026-10-28") == 0 and wt.user_target("7", "2026-10-29") == 4.5
          and wt.user_target("8", "2026-10-28") == 7)
    s = wt.state(A, N)[1]
    check("the person sees what's used", s["leave"]["usedDays"] == 2 and s["leave"]["usedShort"] == 2
          and s["leave"]["policy"]["days"] == 2)

    print("\n--- cancel ---")
    lid = store.one("SELECT id FROM leave_calendar WHERE date='2026-10-30'")["id"]
    check("Priya can't cancel Akash's leave", lv.cancel(P, lid, N)[0] == 404)
    check("Akash cancels his own future leave", lv.cancel(A, lid, N)[0] == 200 and wt.user_target("7", "2026-10-30") == 7)
    old = store.one("SELECT id FROM leave_calendar WHERE date='2026-10-28' AND cancelled_at IS NULL")["id"]
    check("not once the day has passed", lv.cancel(A, old, at(9, day=29))[0] == 400)
    sid = store.one("SELECT id FROM leave_calendar WHERE date='2026-10-31' AND cancelled_at IS NULL")["id"]
    check("Jai can cancel anyone's", lv.cancel(J, sid, at(9, day=29))[0] == 200)

    print("\n--- per person (Jai) ---")
    check("only Jai sets leave", lv.set_policy(A, {"days": 9, "short_count": 0, "short_hours": 0}, N)[0] == 403)
    check("sensible numbers only", lv.set_policy(J, {"user_id": "8", "days": 40, "short_count": 2, "short_hours": 2.5}, N)[0] == 400)
    lv.set_policy(J, {"user_id": "8", "days": 4, "short_count": 1, "short_hours": 2}, N)
    check("Priya gets 4 days + 1 short of 2 h; Akash keeps the default",
          lv.policy("8") == {"days": 4, "short_count": 1, "short_hours": 2.0} and lv.policy("7")["days"] == 2)
    lv.set_policy(J, {"user_id": "*", "days": 3, "short_count": 2, "short_hours": 2.5}, N)
    check("everyone's default changes; Priya's own stays", lv.policy("7")["days"] == 3 and lv.policy("8")["days"] == 4)
    lv.set_policy(J, {"user_id": "*", "days": 2, "short_count": 2, "short_hours": 2.5}, N)
    check("Jai sees everyone's leave", {r["user_id"]: r["usedDays"] for r in wt.state(J, N)[1]["teamLeave"]}["7"] == 1)

    print("\n--- carry forward ---")
    check("unused leave goes to the next work month as hours: 1 day x 7 + 1 short x 2.5",
          lv.carried_hours("7", "2026-12") == 9.5)
    m = wt.month_credit("7", "2026-12", at(9, day=27, month=11))
    check("and counts in that month's balance (9.5 h less the 7 h of 26 Nov not worked)", m["carriedMinutes"] == 570 and m["balanceMinutes"] == 570 - 420)
    check("someone who hadn't started gets nothing carried", lv.carried_hours("8", "2026-12") == 0)
    check("only one month: the month after carries only its own unused leave",
          lv.carried_hours("7", "2027-01") == 1 * 7 + 2 * 2.5)
    print(f"\nAll {PASS} leave checks passed.")


if __name__ == "__main__":
    main()
