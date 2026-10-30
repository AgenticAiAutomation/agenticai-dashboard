"""Tasks v3 Q&A (Jai, 30 Oct): Jai asks one person about their work (optionally a task).

  * only Jai (superusers) and that person ever see the thread
  * open = waiting for the person (red on top of their screen); answered = waiting for Jai
    (on top of his dashboard); Jai replies again (back to open) or says Done
  * Done threads go to history, searchable for HISTORY_DAYS; Jai can reopen one
  * messages are written once (never edited or deleted); questions are never deleted
"""
from datetime import timedelta

from . import service as base, store, taskmgr, worktime as wt

MAX = 2000
HISTORY_DAYS = 366


def _guard(user, now=None, write=False):
    return wt._guard(user, now=now, write=write) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)


def _visible(user):
    """SQL + args limiting questions to what this person may see."""
    return ("1=1", ()) if taskmgr.is_super(user) else ("q.to_user=?", (base.uid(user),))


def _threads(where, args):
    qs = store.rows("SELECT q.*, t.title task_title, p.name to_name FROM questions q "
                    "LEFT JOIN work_tasks t ON t.id=q.task_id LEFT JOIN dt_people p ON p.user_id=q.to_user "
                    f"WHERE {where} ORDER BY q.id DESC LIMIT 300", args)
    names = {p["user_id"]: p["name"] for p in store.rows("SELECT user_id, name FROM dt_people")}
    for q in qs:
        q["messages"] = [{**m, "name": names.get(m["user_id"], m["user_id"])} for m in store.rows(
            "SELECT * FROM question_messages WHERE question_id=? ORDER BY id", (q["id"],))]
    return qs


def inbox(user, now=None):
    g = _guard(user, now)
    if g:
        return g
    where, args = _visible(user)
    out = {"threads": _threads(f"{where} AND q.status!='done'", args), "isSuperuser": taskmgr.is_super(user),
           "me": base.uid(user)}
    if taskmgr.is_super(user):
        out["people"] = [{**p, "tasks": store.rows(
            "SELECT id, title FROM work_tasks WHERE assigned_to=? AND status NOT IN ('accepted','cancelled') "
            "ORDER BY id DESC LIMIT 50", (p["user_id"],))}
            for p in wt.team()]
    return 200, out


def history(user, q="", who="", now=None):
    g = _guard(user, now)
    if g:
        return g
    now = wt._now(now)
    where, args = _visible(user)
    where += " AND q.status='done' AND q.created_at>=?"
    args += (wt._iso(now - timedelta(days=HISTORY_DAYS)),)
    if who and taskmgr.is_super(user):
        where, args = where + " AND q.to_user=?", args + (who,)
    if q:
        where += " AND (t.title LIKE ? OR EXISTS (SELECT 1 FROM question_messages m WHERE m.question_id=q.id AND m.body LIKE ?))"
        args += (f"%{q}%", f"%{q}%")
    return 200, {"threads": _threads(where, args)}


def _say(conn, qid, user_id, body, now):
    conn.execute("INSERT INTO question_messages(question_id, user_id, body, created_at) VALUES (?,?,?,?)",
                 (qid, user_id, body, wt._iso(now)))


def ask(user, body, now=None):
    g = _guard(user, now, write=True) or (None if taskmgr.is_super(user) else wt.ERR_SUPER)
    if g:
        return g
    now = wt._now(now)
    b = body or {}
    who, text = str(b.get("to_user") or ""), str(b.get("question") or "").strip()
    task_id = b.get("task_id") or None
    if not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,)):
        return base._bad("Pick who you're asking.")
    if not 3 <= len(text) <= MAX:
        return base._bad("Write the question (3 to 2000 characters).")
    if task_id and not store.one("SELECT 1 x FROM work_tasks WHERE id=? AND assigned_to=?", (task_id, who)):
        return base._bad("That task isn't theirs.")
    conn = store.connect()
    with conn:
        cur = conn.execute("INSERT INTO questions(to_user, task_id, asked_by, status, created_at) VALUES (?,?,?,?,?)",
                           (who, task_id, base.uid(user), "open", wt._iso(now)))
        _say(conn, cur.lastrowid, base.uid(user), text, now)
    return inbox(user, now)


def _mine(user, qid):
    where, args = _visible(user)
    return store.one(f"SELECT q.* FROM questions q WHERE q.id=? AND {where}", (qid,) + args)


def reply(user, qid, body, now=None):
    """The person answers (-> answered, waiting for Jai) or Jai asks more (-> open)."""
    g = _guard(user, now, write=True)
    if g:
        return g
    now = wt._now(now)
    q = _mine(user, qid)
    if not q or q["status"] == "done":
        return 404, {"error": "not_found", "message": "No open question with that number."}
    text = str((body or {}).get("body") or "").strip()
    if not 1 <= len(text) <= MAX:
        return base._bad("Write your answer (up to 2000 characters).")
    conn = store.connect()
    with conn:
        _say(conn, qid, base.uid(user), text, now)
        conn.execute("UPDATE questions SET status=? WHERE id=?", ("open" if taskmgr.is_super(user) else "answered", qid))
    return inbox(user, now)


def close(user, qid, done=True, now=None):
    """Jai: Done (to history) or reopen a done one."""
    g = _guard(user, now, write=True) or (None if taskmgr.is_super(user) else wt.ERR_SUPER)
    if g:
        return g
    now = wt._now(now)
    q = _mine(user, qid)
    if not q or (q["status"] == "done") == done:
        return 404, {"error": "not_found", "message": "Nothing to do for that question."}
    conn = store.connect()
    with conn:
        conn.execute("UPDATE questions SET status=?, done_by=?, done_at=? WHERE id=?",
                     ("done", base.uid(user), wt._iso(now), qid) if done else ("open", None, None, qid))
        wt._event(conn, q["to_user"], q["task_id"], "question_done" if done else "question_reopen", now,
                  q["status"], "done" if done else "open", f"question #{qid}", actor=base.uid(user))
    return inbox(user, now)
