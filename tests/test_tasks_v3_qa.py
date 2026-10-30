"""Tasks v3 Q&A: Jai asks one person about their work; only the two of them see it; Done goes to
history (a year), Jai can reopen.

Run:  PYTHONPATH="api;." python tests/test_tasks_v3_qa.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="tv3q-")
os.environ.update({
    "DAILY_TRACKER_DB": os.path.join(TMP, "dt.db"), "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk"),
    "DAILY_TRACKER_USER_HOOK": "tests.test_tasks_v3_qa:hook",
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


def at(h, m=0, day=26, month=10, year=2026):
    return datetime(year, month, day, h, m, tzinfo=IST)


def main():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.daily_tracker").register(app)
    wt = importlib.import_module("app.daily_tracker.worktime")
    qa = importlib.import_module("app.daily_tracker.qa")
    service = importlib.import_module("app.daily_tracker.service")
    store = importlib.import_module("app.daily_tracker.store")
    c = TestClient(app)
    for u in USERS.values():
        service.status(u)
    J, A, P = USERS["jai"], USERS["akash"], USERS["priya"]
    cat = store.one("SELECT id FROM task_categories WHERE name='Calling'")["id"]
    t = wt.create_task(J, {"title": "Backlinks for dentalcare.in", "category_id": cat, "details": {"reason": "x"},
                           "assign_to": "7"}, at(9))[1]["task"]["id"]

    print("\n--- asking ---")
    check("only Jai asks", qa.ask(A, {"to_user": "8", "question": "Hi?"}, at(10))[0] == 403)
    check("the task must be theirs", qa.ask(J, {"to_user": "8", "task_id": t, "question": "Status?"}, at(10))[0] == 400)
    code, b = qa.ask(J, {"to_user": "7", "task_id": t, "question": "How many links are live?"}, at(10))
    q1 = b["threads"][0]["id"]
    check("Jai asks Akash about his task", code == 200 and b["threads"][0]["task_title"] == "Backlinks for dentalcare.in")
    qa.ask(J, {"to_user": "8", "question": "Did the client send the logo?"}, at(10, 5))
    a = qa.inbox(A, at(10, 10))[1]
    check("Akash sees only his question, waiting for him", [(x["id"], x["status"]) for x in a["threads"]] == [(q1, "open")])
    check("Priya never sees Akash's", all(x["to_user"] == "8" for x in qa.inbox(P, at(10, 10))[1]["threads"]))
    check("GET /api/tasks/v2/questions answers", c.get("/api/tasks/v2/questions", headers={"x-user": "jai"}).status_code == 200)
    check("Jai sees both, and people with their tasks to ask about",
          len(qa.inbox(J, at(10, 10))[1]["threads"]) == 2
          and [x["title"] for x in next(p for p in qa.inbox(J, at(10, 10))[1]["people"] if p["user_id"] == "7")["tasks"]]
          == ["Backlinks for dentalcare.in"])

    print("\n--- answering ---")
    check("Priya can't answer Akash's", qa.reply(P, q1, {"body": "12"}, at(11))[0] == 404)
    qa.reply(A, q1, {"body": "12 live, 8 pending"}, at(11))
    th = next(x for x in qa.inbox(J, at(11))[1]["threads"] if x["id"] == q1)
    check("answered: now waiting for Jai, thread in order",
          th["status"] == "answered" and [m["body"] for m in th["messages"]] == ["How many links are live?", "12 live, 8 pending"])
    qa.reply(J, q1, {"body": "Send me the 8 pending URLs"}, at(11, 5))
    check("Jai asks more: back to Akash", qa.inbox(A, at(11, 5))[1]["threads"][0]["status"] == "open")
    qa.reply(A, q1, {"body": "Sent on WhatsApp"}, at(11, 30))
    check("only Jai says Done", qa.close(A, q1, True, at(12))[0] == 403)
    qa.close(J, q1, True, at(12))
    check("Done: off both screens", all(x["id"] != q1 for x in qa.inbox(A, at(12))[1]["threads"] + qa.inbox(J, at(12))[1]["threads"]))

    print("\n--- history ---")
    h = qa.history(A, "", "", at(12, day=26, month=10, year=2026))[1]["threads"]
    check("Akash finds it in his history with the whole thread", [x["id"] for x in h] == [q1] and len(h[0]["messages"]) == 4)
    check("search by words in the thread or the task", qa.history(J, "WhatsApp", "", at(12))[1]["threads"][0]["id"] == q1
          and qa.history(J, "dentalcare", "", at(12))[1]["threads"][0]["id"] == q1
          and qa.history(J, "nothing like this", "", at(12))[1]["threads"] == [])
    check("Priya's history doesn't show it", qa.history(P, "", "", at(12))[1]["threads"] == [])
    check("Jai filters by person", qa.history(J, "", "8", at(12))[1]["threads"] == [])
    check("still there 11 months later", [x["id"] for x in qa.history(J, "", "", at(12, day=20, month=9, year=2027))[1]["threads"]] == [q1])
    check("Jai reopens it: back on top for Akash", qa.close(J, q1, False, at(13))[0] == 200
          and qa.inbox(A, at(13))[1]["threads"][0]["id"] == q1)

    print("\n--- guardrails ---")
    conn = store.connect()
    for sql in ("DELETE FROM questions", "DELETE FROM question_messages", "UPDATE question_messages SET body='edited'",
                "UPDATE questions SET to_user='8'"):
        try:
            with conn:
                conn.execute(sql)
            ok = False
        except sqlite3.DatabaseError:
            ok = True
        check(f"refused: {sql}", ok)
    wt.settings.TASKS_V3 = False
    check("v3 off: 404", qa.inbox(A, at(13))[0] == 404)
    print(f"\nAll {PASS} Q&A checks passed.")


if __name__ == "__main__":
    main()
