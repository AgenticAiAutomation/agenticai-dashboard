"""Task manager (T7) — SMART tasks, auto progress, targets, Red/Amber/Green,
Mirror, points, tiers and badges. Flag FEATURE_TASK_MANAGER.

Same contract as service.py: every function takes the user dict
({id, name, email, role}) or None, returns (http_status, payload).

Units — what a task (or a target) counts:
    backlinks   links logged on Backlink Ops (not rejected), that site, that person
    blogs       articles assigned to the person and published (seo_articles)
    ideas       ideas the person submitted (the weekly idea task)
    wt:<id>     APPROVED Daily Tracker logs of that work type
    anything    else: counted by hand — the assignee adds qty + a proof link
Synced progress is rebuilt from its source on every read and keyed by the
source row, so nothing counts twice and a rejected link stops counting.

Times are IST wall-clock strings "YYYY-MM-DDTHH:MM".
"""
import calendar
import csv
import io
import math
from datetime import date as _date, datetime, timedelta

from . import service as base
from . import store
from .config import settings

GOALS = ("traffic", "leads", "rankings")
PRIORITIES = ("P1", "P2", "P3")
RECURRENCE = ("none", "daily", "weekly", "monthly")
STATUSES = ("todo", "in_progress", "submitted", "approved", "needs_fix", "blocked")
AUTO_UNITS = {"backlinks": "backlinks (Backlink Ops)", "blogs": "blogs published", "ideas": "ideas"}
UNIT_MARKS = {"backlinks": 5, "blogs": 20, "ideas": 0}
ON_TIME_BONUS = 0.10
STREAK_RUN, STREAK_POINTS = 7, 50
IDEA_POINTS = {"submitted": 5, "trialled": 20, "worked": 100}
LOAD_LIMIT = 40
DAY_START, DAY_END = 9, 19          # working hours (IST) for "expected by now" today

ERR_OFF = (404, {"error": "disabled", "message": "The task manager is not switched on."})
ERR_SUPER = (403, {"error": "forbidden", "message": "Only Jai can change that."})
ERR_VIEWER = (403, {"error": "read_only_user", "message": "Your account can read tasks but not change them."})


# ------------------------------------------------------------------ who / when
def is_super(user):
    return bool(user) and str(user.get("email") or "").strip().lower() in settings.SUPERUSERS


def is_viewer(user):
    return str((user or {}).get("role") or "").lower() == "viewer"


def _guard(user, write=False, admin=False, superuser=False):
    if not settings.TASKS:
        return ERR_OFF
    if not user:
        return base.ERR_AUTH
    if superuser and not is_super(user):
        return ERR_SUPER
    if admin and not base.is_admin(user):
        return base.ERR_ADMIN
    if write and is_viewer(user):
        return ERR_VIEWER
    if write and settings.READ_ONLY:
        return base.ERR_FROZEN
    return None


def now_ist():
    return datetime.now(store.IST).replace(tzinfo=None, second=0, microsecond=0)


def _dt(s):
    s = str(s or "").strip().replace(" ", "T")
    if len(s) == 10:
        s += "T00:00"
    return datetime.fromisoformat(s[:16])


def _fmt(d):
    return d.strftime("%Y-%m-%dT%H:%M")


def _month_of(d):
    return d.isoformat()[:7] if isinstance(d, _date) else str(d)[:7]


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# ------------------------------------------------------------------ units + sources
def unit_label(unit):
    if unit in AUTO_UNITS:
        return AUTO_UNITS[unit]
    if str(unit).startswith("wt:"):
        t = store.one("SELECT name FROM work_types WHERE id=?", (unit[3:],))
        return t["name"] if t else unit
    return unit


def is_auto(unit):
    return unit in AUTO_UNITS or str(unit).startswith("wt:")


def _blog_rows(user_id, d_from, d_to):
    """Articles assigned to this dashboard user, published in [d_from, d_to]
    (IST dates). Read-only, from the dashboard's Postgres; [] if unreachable."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return []
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            got = db.execute(text(
                "SELECT slug, (published_at AT TIME ZONE 'Asia/Kolkata')::date AS d FROM seo_articles "
                "WHERE assigned_to = :u AND published_at IS NOT NULL "
                "AND (published_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN :a AND :b"),
                {"u": uid, "a": d_from, "b": d_to}).fetchall()
        finally:
            db.close()
        return [{"slug": r[0], "date": str(r[1])} for r in got]
    except Exception:
        return []


BLOG_SOURCE = _blog_rows          # tests replace this
BLOG_SITE = "agenticai"           # the only site this dashboard publishes to
BLOG_URL = "https://agenticaiautomation.co/blog/{slug}"


def source_items(unit, person, project, d_from, d_to):
    """[(source, source_id, qty, proof_url, date)] counted for `unit`.
    person = {"user_id", "name"}; dates are 'YYYY-MM-DD' inclusive."""
    d_from, d_to = str(d_from)[:10], str(d_to)[:10]
    out = []
    if unit == "backlinks":
        for b in base.backlink_rows([person["name"]], d_from, d_to):
            if b["status"] != "rejected" and (not project or b["project"] == project):
                out.append(("backlink", b["id"], 1, b["url"], b["date"]))
    elif unit == "blogs":
        if not project or project == BLOG_SITE:
            for b in BLOG_SOURCE(person["user_id"], d_from, d_to):
                out.append(("blog", b["slug"], 1, BLOG_URL.format(slug=b["slug"]), b["date"]))
    elif unit == "ideas":
        for i in store.rows("SELECT id, created_at FROM ideas WHERE user_id=? "
                            "AND substr(created_at,1,10) BETWEEN ? AND ?",
                            (person["user_id"], d_from, d_to)):
            out.append(("idea", str(i["id"]), 1, "", i["created_at"][:10]))
    elif str(unit).startswith("wt:"):
        sql = ("SELECT id, proof_url, log_date FROM daily_logs WHERE user_id=? AND status='approved' "
               "AND work_type_id=? AND log_date BETWEEN ? AND ?")
        args = [person["user_id"], int(unit[3:]), d_from, d_to]
        if project:
            sql += " AND project_id=?"
            args.append(project)
        for r in store.rows(sql, args):
            out.append(("daily_log", str(r["id"]), 1, r["proof_url"], r["log_date"]))
    return out


def actual(unit, person, project, d_from, d_to):
    if is_auto(unit):
        return float(sum(x[2] for x in source_items(unit, person, project, d_from, d_to)))
    r = store.one("SELECT COALESCE(SUM(p.qty),0) q FROM task_progress p JOIN tasks t ON t.id=p.task_id "
                  "WHERE p.user_id=? AND p.source='manual' AND t.unit=? AND t.project_id=? "
                  "AND substr(p.created_at,1,10) BETWEEN ? AND ?",
                  (person["user_id"], unit, project, str(d_from)[:10], str(d_to)[:10]))
    return float(r["q"] if r else 0)


# ------------------------------------------------------------------ people
def _person(user_id):
    p = store.one("SELECT user_id, name, email, role FROM dt_people WHERE user_id=?", (str(user_id),))
    return p or {"user_id": str(user_id), "name": "", "email": "", "role": ""}


def people(user):
    g = _guard(user)
    if g:
        return g
    base._seen(user)
    if not base.is_admin(user):
        return 200, {"people": [_person(base.uid(user))]}
    return 200, {"people": store.rows("SELECT user_id, name, email, role FROM dt_people ORDER BY lower(name)")}


# ------------------------------------------------------------------ tasks: read
def _rag_settings():
    r = store.one("SELECT green_min, amber_min FROM rag_settings WHERE id=1")
    return {"green_min": r["green_min"], "amber_min": r["amber_min"]} if r else {"green_min": 90, "amber_min": 60}


def task_rag(t, progress, now=None, rs=None):
    """('green'|'amber'|'red', why). Rules in spec 7.4; thresholds editable."""
    now, rs = now or now_ist(), rs or _rag_settings()
    if t["status"] == "approved":
        return "green", "Approved"
    if t["status"] == "submitted":
        return "green", "Submitted for review"
    start, due = _dt(t["start_at"]), _dt(t["due_at"])
    target = float(t["target_qty"] or 0)
    if now > due:
        return "red", "Overdue"
    if now <= start:
        return "green", "Not started yet"
    frac = min(1.0, (now - start) / (due - start)) if due > start else 1.0
    expected = target * frac
    pct = 100.0 if expected <= 0 else progress / expected * 100
    if progress >= target and target > 0:
        pct = max(pct, 100.0)
    if pct < rs["amber_min"]:
        return "red", f"{round(pct)}% of where it should be by now"
    if due - now <= timedelta(hours=24):
        return "amber", "Due within 24 hours and not submitted"
    if pct < rs["green_min"]:
        return "amber", f"{round(pct)}% of where it should be by now"
    return "green", "On track"


def _assignees(task_id):
    return store.rows("SELECT user_id, user_name FROM task_assignees WHERE task_id=? ORDER BY user_name", (task_id,))


def sync_task(t):
    """Rebuild a task's synced progress from its source. Approved tasks are frozen."""
    if t["status"] == "approved" or not is_auto(t["unit"]):
        return
    d_from, d_to = t["start_at"][:10], min(t["due_at"][:10], now_ist().date().isoformat())
    conn = store.connect()
    with conn:
        conn.execute("DELETE FROM task_progress WHERE task_id=? AND source != 'manual'", (t["id"],))
        if d_to < d_from:
            return
        for a in _assignees(t["id"]):
            person = {"user_id": a["user_id"], "name": a["user_name"]}
            for src, sid, qty, proof, _ in source_items(t["unit"], person, t["project_id"], d_from, d_to):
                conn.execute("INSERT OR IGNORE INTO task_progress(task_id, user_id, qty, source, source_id, "
                             "proof_url, created_at) VALUES (?,?,?,?,?,?,?)",
                             (t["id"], a["user_id"], qty, src, sid, proof, store.now_iso()))


def _progress(task_id):
    r = store.one("SELECT COALESCE(SUM(qty),0) q FROM task_progress WHERE task_id=?", (task_id,))
    return float(r["q"])


def _public(t, detail=False, rs=None, known=None):
    prog = _progress(t["id"])
    rag, why = task_rag(t, prog, rs=rs)
    out = dict(t)
    out.update({"assignees": _assignees(t["id"]), "progress": prog,
                "pct": round(min(1.0, prog / t["target_qty"]) * 100) if t["target_qty"] else 0,
                "rag": rag, "ragWhy": why, "unitLabel": unit_label(t["unit"]),
                "auto": is_auto(t["unit"]),
                "site": ((known or {}).get(t["project_id"]) or {}).get("short", t["project_id"]),
                "checklist": store.rows("SELECT id, text, done FROM task_checklist WHERE task_id=? ORDER BY id",
                                        (t["id"],))})
    if detail:
        out["links"] = store.rows("SELECT id, url, label FROM task_links WHERE task_id=? ORDER BY id", (t["id"],))
        out["comments"] = store.rows("SELECT * FROM task_comments WHERE task_id=? ORDER BY id", (t["id"],))
        out["entries"] = store.rows("SELECT p.*, a.user_name FROM task_progress p LEFT JOIN task_assignees a "
                                    "ON a.task_id=p.task_id AND a.user_id=p.user_id WHERE p.task_id=? "
                                    "ORDER BY p.id DESC LIMIT 200", (t["id"],))
    return out


def _visible(user, t):
    if base.is_admin(user):
        return True
    return bool(store.one("SELECT 1 x FROM task_assignees WHERE task_id=? AND user_id=?",
                          (t["id"], base.uid(user))))


def list_tasks(user, scope="mine", user_id=None, project_id=None, status=None, due_before=None):
    g = _guard(user)
    if g:
        return g
    base._seen(user)
    ensure_weekly_idea(user)
    roll_recurring()
    admin = base.is_admin(user)
    sql, args = "SELECT DISTINCT t.* FROM tasks t LEFT JOIN task_assignees a ON a.task_id=t.id WHERE 1=1", []
    if not admin or scope != "all":
        sql += " AND a.user_id=?"
        args.append(str(user_id) if (admin and user_id) else base.uid(user))
    elif user_id:
        sql += " AND a.user_id=?"
        args.append(str(user_id))
    if project_id:
        sql += " AND t.project_id=?"
        args.append(project_id)
    if status in STATUSES:
        sql += " AND t.status=?"
        args.append(status)
    if due_before:
        sql += " AND t.due_at<=?"
        args.append(str(due_before)[:10] + "T23:59")
    rows = store.rows(sql + " ORDER BY t.due_at, t.priority", args)
    for t in rows:
        sync_task(t)
    rs = _rag_settings()
    known, _ = base.sites(user)
    return 200, {"tasks": [_public(t, rs=rs, known=known) for t in rows], "now": _fmt(now_ist()),
                 "statuses": STATUSES, "rag": rs}


def get_task(user, task_id):
    g = _guard(user)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    sync_task(t)
    known, _ = base.sites(user)
    return 200, {"task": _public(t, detail=True, known=known)}


# ------------------------------------------------------------------ tasks: write
def _smart(user, body, existing=None):
    """Validate the SMART fields. Returns (error, clean)."""
    b = dict(existing or {})
    b.update({k: v for k, v in (body or {}).items() if v is not None})
    missing = []
    title = str(b.get("title") or "").strip()
    desc = str(b.get("description") or "").strip()
    if len(title) < 5:
        missing.append("Specific: a clear title")
    if len(desc) < 10:
        missing.append("Specific: the deliverable, in a sentence")
    known, _ = base.sites(user)
    project = str(b.get("project_id") or "")
    if project not in known:
        missing.append("Relevant: the website")
    goal = str(b.get("goal") or "")
    if goal not in GOALS:
        missing.append("Relevant: the goal it supports (traffic / leads / rankings)")
    try:
        qty = float(b.get("target_qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        missing.append("Measurable: a target number")
    unit = str(b.get("unit") or "").strip()[:60]
    if not unit:
        missing.append("Measurable: the unit (blogs, backlinks, posts…)")
    if unit.startswith("wt:") and not store.one("SELECT id FROM work_types WHERE id=?", (unit[3:],)):
        missing.append("Measurable: that work type no longer exists")
    proof = str(b.get("proof_type") or "").strip()[:40]
    if not proof:
        missing.append("Measurable: the proof type (link)")
    try:
        effort = float(b.get("effort_hours") or 0)
    except (TypeError, ValueError):
        effort = 0
    if effort <= 0:
        missing.append("Achievable: effort in hours")
    try:
        start, due = _dt(b.get("start_at")), _dt(b.get("due_at"))
        if due <= start:
            missing.append("Time-bound: the due time must be after the start")
    except (TypeError, ValueError):
        start = due = None
        missing.append("Time-bound: start and due date")
    pri = str(b.get("priority") or "")
    if pri not in PRIORITIES:
        missing.append("Priority: P1, P2 or P3")
    rec = str(b.get("recurrence") or "none")
    if rec not in RECURRENCE:
        missing.append("Recurrence: none, daily, weekly or monthly")
    ass = b.get("assignees")
    ass = [str(a) for a in ass] if isinstance(ass, list) else None
    if existing is None and not ass:
        missing.append("Assignee: at least one person")
    if ass:
        unknown = [a for a in ass if not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (a,))]
        if unknown:
            missing.append("Assignee: someone who has opened the tracker at least once")
    if missing:
        return (400, {"error": "not_smart", "message": "Every SMART field is needed: " + "; ".join(missing) + ".",
                      "missing": missing}), None
    marks = b.get("marks")
    try:
        marks = float(marks) if marks not in (None, "") else None
    except (TypeError, ValueError):
        marks = None
    if marks is None:
        if unit.startswith("wt:"):
            wt = store.one("SELECT base_marks FROM work_types WHERE id=?", (unit[3:],))
            marks = float(wt["base_marks"]) * qty
        else:
            marks = float(UNIT_MARKS.get(unit, 3)) * qty
    clean = {"title": title[:140], "description": desc[:2000], "project_id": project, "goal": goal,
             "target_qty": qty, "unit": unit, "proof_type": proof, "effort_hours": effort,
             "priority": pri, "start_at": _fmt(start), "due_at": _fmt(due), "recurrence": rec,
             "marks": round(max(0.0, min(5000.0, marks)), 2),
             "work_type_id": int(unit[3:]) if unit.startswith("wt:") else None}
    return None, (clean, ass)


def _load_warnings(assignees, start, due, exclude=None):
    """Spec 7.1 'Achievable': warn when someone's open work for that week is over 40 h."""
    ws = _dt(due).date() - timedelta(days=_dt(due).weekday())
    we = ws + timedelta(days=6)
    out = []
    for a in assignees:
        r = store.one("SELECT COALESCE(SUM(t.effort_hours),0) h FROM tasks t JOIN task_assignees x ON x.task_id=t.id "
                      "WHERE x.user_id=? AND t.status NOT IN ('approved') AND substr(t.start_at,1,10)<=? "
                      "AND substr(t.due_at,1,10)>=?" + (" AND t.id != ?" if exclude else ""),
                      (a, we.isoformat(), ws.isoformat()) + ((exclude,) if exclude else ()))
        h = float(r["h"])
        if h > LOAD_LIMIT:
            out.append(f"{_person(a)['name'] or a} already has {round(h)} h of open work in the week of "
                       f"{ws.isoformat()} — over {LOAD_LIMIT} h.")
    return out


def create_task(user, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    err, ok = _smart(user, body)
    if err:
        return err
    clean, ass = ok
    now = store.now_iso()
    cur = store.write(
        "INSERT INTO tasks(title, description, project_id, goal, target_qty, unit, work_type_id, proof_type, "
        "effort_hours, priority, start_at, due_at, recurrence, marks, status, created_by, created_by_name, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'todo',?,?,?,?)",
        (clean["title"], clean["description"], clean["project_id"], clean["goal"], clean["target_qty"],
         clean["unit"], clean["work_type_id"], clean["proof_type"], clean["effort_hours"], clean["priority"],
         clean["start_at"], clean["due_at"], clean["recurrence"], clean["marks"], base.uid(user),
         user.get("name") or "", now, now))
    tid = cur.lastrowid
    if clean["recurrence"] != "none":
        store.write("UPDATE tasks SET series_id=? WHERE id=?", (tid, tid))
    for a in ass:
        store.write("INSERT OR IGNORE INTO task_assignees(task_id, user_id, user_name) VALUES (?,?,?)",
                    (tid, a, _person(a)["name"]))
    for item in (body or {}).get("checklist") or []:
        if str(item).strip():
            store.write("INSERT INTO task_checklist(task_id, text) VALUES (?,?)", (tid, str(item).strip()[:200]))
    for link in (body or {}).get("links") or []:
        url = str((link or {}).get("url") if isinstance(link, dict) else link).strip()
        if base._valid_url(url):
            store.write("INSERT INTO task_links(task_id, url, label) VALUES (?,?,?)",
                        (tid, url, str((link or {}).get("label", "") if isinstance(link, dict) else "")[:80]))
    known, _ = base.sites(user)
    return 201, {"task": _public(store.one("SELECT * FROM tasks WHERE id=?", (tid,)), detail=True, known=known),
                 "warnings": _load_warnings(ass, clean["start_at"], clean["due_at"])}


def update_task(user, task_id, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        return 404, {"error": "not_found", "message": "No such task."}
    if t["status"] == "approved":
        return base._bad("An approved task is final.")
    existing = dict(t)
    if t["work_type_id"]:
        existing["unit"] = t["unit"]
    err, ok = _smart(user, body, existing=existing)
    if err:
        return err
    clean, ass = ok
    store.write("UPDATE tasks SET title=?, description=?, project_id=?, goal=?, target_qty=?, unit=?, "
                "work_type_id=?, proof_type=?, effort_hours=?, priority=?, start_at=?, due_at=?, recurrence=?, "
                "marks=?, updated_at=? WHERE id=?",
                (clean["title"], clean["description"], clean["project_id"], clean["goal"], clean["target_qty"],
                 clean["unit"], clean["work_type_id"], clean["proof_type"], clean["effort_hours"],
                 clean["priority"], clean["start_at"], clean["due_at"], clean["recurrence"], clean["marks"],
                 store.now_iso(), task_id))
    if ass:
        store.write("DELETE FROM task_assignees WHERE task_id=?", (task_id,))
        for a in ass:
            store.write("INSERT OR IGNORE INTO task_assignees(task_id, user_id, user_name) VALUES (?,?,?)",
                        (task_id, a, _person(a)["name"]))
    return get_task(user, task_id)


def delete_task(user, task_id):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        return 404, {"error": "not_found", "message": "No such task."}
    if t["status"] == "approved" or store.one("SELECT 1 x FROM task_progress WHERE task_id=? AND source='manual'",
                                              (task_id,)):
        return base._bad("This task has approved work or logged progress — keep it for the record.")
    store.write("DELETE FROM tasks WHERE id=?", (task_id,))
    return 200, {"deleted": task_id}


# Who may move a task where. Assignees drive the work; admins approve.
ASSIGNEE_MOVES = {
    "todo": {"in_progress", "blocked", "submitted"},
    "in_progress": {"submitted", "blocked", "todo"},
    "blocked": {"in_progress", "todo"},
    "needs_fix": {"in_progress", "submitted", "blocked"},
    "submitted": {"in_progress"},
}


def set_status(user, task_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    new = str((body or {}).get("status") or "")
    if new in ("approved", "needs_fix"):
        return base._bad("Use approve / needs fix for that.")
    if new not in ASSIGNEE_MOVES.get(t["status"], set()):
        return base._bad(f"A task that is {t['status'].replace('_', ' ')} can't move to {new.replace('_', ' ')}.")
    reason = str((body or {}).get("reason") or "").strip()
    if new == "blocked" and len(reason) < 5:
        return base._bad("Say what is blocking it.")
    if new == "submitted":
        sync_task(t)
        if t["unit"] != "ideas" and _progress(task_id) <= 0:
            return base._bad("Add progress first — nothing has been counted on this task yet.")
    store.write("UPDATE tasks SET status=?, blocked_reason=?, submitted_at=COALESCE(?, submitted_at), "
                "updated_at=? WHERE id=?",
                (new, reason if new == "blocked" else "",
                 _fmt(now_ist()) if new == "submitted" else None, store.now_iso(), task_id))
    if reason:
        _comment(user, task_id, f"Blocked: {reason}" if new == "blocked" else reason)
    return get_task(user, task_id)


def approve(user, task_id, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    body = body or {}
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        return 404, {"error": "not_found", "message": "No such task."}
    decision = body.get("status")
    if decision not in ("approved", "needs_fix"):
        return base._bad("Decide approved or needs_fix.")
    if t["status"] not in ("submitted", "needs_fix", "in_progress", "todo", "blocked"):
        return base._bad("This task is already approved.")
    note = str(body.get("note") or "").strip()[:500]
    if decision == "needs_fix":
        store.write("UPDATE tasks SET status='needs_fix', rework=rework+1, review_note=?, updated_at=? WHERE id=?",
                    (note, store.now_iso(), task_id))
        if note:
            _comment(user, task_id, "Needs fix: " + note)
        return get_task(user, task_id)
    try:
        q = int(body.get("quality") or 3)
    except (TypeError, ValueError):
        q = 3
    if q not in base.QUALITY:
        return base._bad("Quality is 1 to 5.")
    sync_task(t)
    store.write("UPDATE tasks SET status='approved', quality=?, approved_at=?, approved_by=?, review_note=?, "
                "submitted_at=COALESCE(submitted_at, ?), updated_at=? WHERE id=?",
                (q, _fmt(now_ist()), user.get("name") or "admin", note, _fmt(now_ist()), store.now_iso(), task_id))
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    on_time = t["submitted_at"] and t["submitted_at"] <= t["due_at"]
    pts = round(float(t["marks"]) * base.QUALITY[q] * (1 + ON_TIME_BONUS if on_time else 1), 2)
    month = (t["approved_at"] or "")[:7]
    for a in _assignees(task_id):
        _ledger(a["user_id"], a["user_name"], pts, "task", "task", task_id, month)
        _level_xp(a["user_id"], t["project_id"], pts, f"task:{task_id}")
    _spawn_next(t)
    out = get_task(user, task_id)
    out[1]["points"] = pts
    out[1]["onTime"] = bool(on_time)
    return out


def _level_xp(user_id, project, xp, ref):
    """Spec 7.2: approved task marks go to the person's level XP on that site (T2)."""
    try:
        from app.backlink_ops.config import settings as bo_settings
        if not bo_settings.ENABLED:
            return
        from app.backlink_ops import store as bo_store
        bo_store.add_level_bonus(str(user_id), project, xp, ref)
    except Exception:
        pass


def add_progress(user, task_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    if is_auto(t["unit"]):
        return base._bad(f"This task counts {unit_label(t['unit'])} automatically — log the work where you "
                         "normally do and it shows up here. No double entry.")
    if t["status"] == "approved":
        return base._bad("An approved task is final.")
    body = body or {}
    url = str(body.get("proof_url") or "").strip()
    if not base._valid_url(url):
        return base._bad("A proof link (http/https) is required.")
    try:
        qty = float(body.get("qty") or 1)
    except (TypeError, ValueError):
        return base._bad("Quantity must be a number.")
    if not 0 < qty <= 1000:
        return base._bad("Quantity must be between 1 and 1000.")
    key = base.proof_key(url)
    if store.one("SELECT 1 x FROM task_progress WHERE task_id=? AND source='manual' AND source_id=?", (task_id, key)):
        return base._bad("That proof link is already counted on this task.", "duplicate", 409)
    store.write("INSERT INTO task_progress(task_id, user_id, qty, source, source_id, proof_url, created_at) "
                "VALUES (?,?,?,'manual',?,?,?)", (task_id, base.uid(user), qty, key, url, store.now_iso()))
    if t["status"] == "todo":
        store.write("UPDATE tasks SET status='in_progress', updated_at=? WHERE id=?", (store.now_iso(), task_id))
    return get_task(user, task_id)


def _comment(user, task_id, text):
    store.write("INSERT INTO task_comments(task_id, user_id, user_name, text, created_at) VALUES (?,?,?,?,?)",
                (task_id, base.uid(user), user.get("name") or "", text[:1000], store.now_iso()))


def add_comment(user, task_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    text = str((body or {}).get("text") or "").strip()
    if not text:
        return base._bad("Write something first.")
    _comment(user, task_id, text)
    return get_task(user, task_id)


def add_checklist(user, task_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    text = str((body or {}).get("text") or "").strip()
    if not text:
        return base._bad("Write the item first.")
    store.write("INSERT INTO task_checklist(task_id, text) VALUES (?,?)", (task_id, text[:200]))
    return get_task(user, task_id)


def toggle_checklist(user, task_id, item_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    store.write("UPDATE task_checklist SET done=? WHERE id=? AND task_id=?",
                (1 if (body or {}).get("done") else 0, item_id, task_id))
    return get_task(user, task_id)


def add_link(user, task_id, body):
    g = _guard(user, write=True)
    if g:
        return g
    t = store.one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t or not _visible(user, t):
        return 404, {"error": "not_found", "message": "No such task."}
    url = str((body or {}).get("url") or "").strip()
    if not base._valid_url(url):
        return base._bad("Paste a full link starting with http:// or https://.")
    store.write("INSERT INTO task_links(task_id, url, label) VALUES (?,?,?)",
                (task_id, url, str((body or {}).get("label") or "")[:80]))
    return get_task(user, task_id)


# ------------------------------------------------------------------ recurrence + weekly idea
def _next_window(t, now):
    start, due = _dt(t["start_at"]), _dt(t["due_at"])
    step = {"daily": lambda d, n: d + timedelta(days=n), "weekly": lambda d, n: d + timedelta(weeks=n),
            "monthly": lambda d, n: _add_months(d, n)}[t["recurrence"]]
    n = 1
    while step(due, n) <= now and n < 400:     # skip missed periods: no pile of overdue copies
        n += 1
    return step(start, n), step(due, n)


def _spawn_next(t):
    if t["recurrence"] == "none":
        return None
    series = t["series_id"] or t["id"]
    ns, nd = _next_window(t, now_ist())
    if store.one("SELECT id FROM tasks WHERE series_id=? AND start_at>=?", (series, _fmt(ns))):
        return None
    now = store.now_iso()
    try:
        cur = store.write(
            "INSERT INTO tasks(title, description, project_id, goal, target_qty, unit, work_type_id, proof_type, "
            "effort_hours, priority, start_at, due_at, recurrence, series_id, marks, status, created_by, "
            "created_by_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'todo',?,?,?,?)",
            (t["title"], t["description"], t["project_id"], t["goal"], t["target_qty"], t["unit"],
             t["work_type_id"], t["proof_type"], t["effort_hours"], t["priority"], _fmt(ns), _fmt(nd),
             t["recurrence"], series, t["marks"], t["created_by"], t["created_by_name"], now, now))
    except Exception:
        return None                                   # another worker made it first
    new = cur.lastrowid
    for a in _assignees(t["id"]):
        store.write("INSERT OR IGNORE INTO task_assignees(task_id, user_id, user_name) VALUES (?,?,?)",
                    (new, a["user_id"], a["user_name"]))
    for c in store.rows("SELECT text FROM task_checklist WHERE task_id=?", (t["id"],)):
        store.write("INSERT INTO task_checklist(task_id, text) VALUES (?,?)", (new, c["text"]))
    return new


def roll_recurring():
    """A recurring task whose due time has passed gets its next copy, even if
    nobody approved it — the next period still has work in it."""
    now = _fmt(now_ist())
    for t in store.rows("SELECT * FROM tasks WHERE recurrence != 'none' AND due_at < ? AND id IN "
                        "(SELECT MAX(id) FROM tasks WHERE recurrence != 'none' GROUP BY COALESCE(series_id, id))",
                        (now,)):
        _spawn_next(t)


def ensure_weekly_idea(user):
    """Spec 7.6: one idea per person per week, due Friday 18:00 IST, as a task."""
    if not (settings.IDEAS and user) or base.is_admin(user) or is_viewer(user):
        return
    _, allowed = base.sites(user)
    if not allowed:
        return
    today = now_ist().date()
    monday = today - timedelta(days=today.weekday())
    week = iso_week(today)
    uid = base.uid(user)
    if store.one("SELECT id FROM tasks WHERE kind='weekly_idea' AND week=? AND created_by=?", (week, uid)):
        return
    now = store.now_iso()
    try:
        cur = store.write(
            "INSERT INTO tasks(title, description, project_id, goal, target_qty, unit, proof_type, effort_hours, "
            "priority, start_at, due_at, recurrence, marks, status, kind, week, created_by, created_by_name, "
            "created_at, updated_at) VALUES (?,?,?,?,1,'ideas','idea',1,'P2',?,?,'none',0,'todo','weekly_idea',?,?,"
            "'system',?,?)",
            (f"Weekly idea · {week}", "Submit one revolutionary idea for the company or your website on the "
             "Idea Board: problem, idea, how to test it in 2 weeks, success metric, effort.",
             allowed[0], "traffic", _fmt(datetime.combine(monday, datetime.min.time()).replace(hour=9)),
             _fmt(datetime.combine(monday + timedelta(days=4), datetime.min.time()).replace(hour=18)),
             week, uid, now, now))
    except Exception:
        return
    store.write("INSERT OR IGNORE INTO task_assignees(task_id, user_id, user_name) VALUES (?,?,?)",
                (cur.lastrowid, uid, user.get("name") or ""))


def idea_submitted(user):
    """Called by service.create_idea: completes this week's idea task."""
    if not settings.TASKS:
        return
    ensure_weekly_idea(user)
    week = iso_week(now_ist().date())
    t = store.one("SELECT * FROM tasks WHERE kind='weekly_idea' AND week=? AND created_by=?",
                  (week, base.uid(user)))
    if t and t["status"] != "approved":
        sync_task(t)
        store.write("UPDATE tasks SET status='approved', submitted_at=COALESCE(submitted_at, ?), approved_at=?, "
                    "approved_by='system', updated_at=? WHERE id=?",
                    (_fmt(now_ist()), _fmt(now_ist()), store.now_iso(), t["id"]))


# ------------------------------------------------------------------ targets (7.3)
def _workdays(month):
    y, m = int(month[:4]), int(month[5:7])
    return [_date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)
            if _date(y, m, d).weekday() in settings.WORKDAYS]


def _leave(user_id, d_from, d_to):
    return {r["date"] for r in store.rows("SELECT date FROM leave_days WHERE user_id IN (?, '*') "
                                          "AND date BETWEEN ? AND ?", (str(user_id), d_from, d_to))}


def daily_plan(user_id, project, unit, month):
    """{date: qty} for every day of the month. Working days share the monthly
    target evenly (or a week's override evenly); leave days and non-working
    days are 0 — a leave day lowers the target, it is not pushed onto others."""
    t = store.one("SELECT qty FROM task_targets WHERE user_id=? AND project_id=? AND unit=? AND month=?",
                  (str(user_id), project, unit, month))
    days = _workdays(month)
    y, m = int(month[:4]), int(month[5:7])
    allday = [_date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    plan = {d.isoformat(): 0.0 for d in allday}
    if not t or not days:
        return plan
    per = float(t["qty"]) / len(days)
    for d in days:
        plan[d.isoformat()] = per
    for o in store.rows("SELECT week_start, qty FROM target_splits WHERE user_id=? AND project_id=? AND unit=? "
                        "AND month=?", (str(user_id), project, unit, month)):
        ws = _date.fromisoformat(o["week_start"])
        wdays = [d for d in days if ws <= d <= ws + timedelta(days=6)]
        for d in wdays:
            plan[d.isoformat()] = float(o["qty"]) / len(wdays)
    for d in _leave(user_id, allday[0].isoformat(), allday[-1].isoformat()):
        if d in plan:
            plan[d] = 0.0
    return plan


def plan(user, user_id=None, month=None):
    g = _guard(user)
    if g:
        return g
    who = str(user_id) if (user_id and base.is_admin(user)) else base.uid(user)
    month = (month or now_ist().date().isoformat())[:7]
    out = []
    for t in store.rows("SELECT * FROM task_targets WHERE user_id=? AND month=? ORDER BY project_id, unit",
                        (who, month)):
        days = daily_plan(who, t["project_id"], t["unit"], month)
        weeks = {}
        for d, q in days.items():
            dd = _date.fromisoformat(d)
            ws = (dd - timedelta(days=dd.weekday())).isoformat()
            weeks[ws] = weeks.get(ws, 0) + q
        overrides = {o["week_start"] for o in store.rows(
            "SELECT week_start FROM target_splits WHERE user_id=? AND project_id=? AND unit=? AND month=?",
            (who, t["project_id"], t["unit"], month))}
        out.append({"project": t["project_id"], "unit": t["unit"], "unitLabel": unit_label(t["unit"]),
                    "month": month, "qty": t["qty"],
                    "weeks": [{"weekStart": w, "qty": round(q, 1), "edited": w in overrides}
                              for w, q in sorted(weeks.items())],
                    "days": {d: round(q, 2) for d, q in days.items()}})
    y, m = int(month[:4]), int(month[5:7])
    leave = sorted(_leave(who, f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}"))
    return 200, {"userId": who, "month": month, "targets": out, "leave": leave,
                 "workdays": settings.WORKDAYS, "units": _unit_choices()}


def _unit_choices():
    out = [{"unit": k, "label": v} for k, v in AUTO_UNITS.items() if k != "ideas"]
    for t in store.rows("SELECT id, name, base_marks FROM work_types WHERE active=1 AND kind != 'backlink' "
                        "ORDER BY sort_order"):
        out.append({"unit": f"wt:{t['id']}", "label": t["name"], "marks": t["base_marks"]})
    return out


def set_target(user, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    b = body or {}
    who, project, unit = str(b.get("user_id") or ""), str(b.get("project_id") or ""), str(b.get("unit") or "")
    month = str(b.get("month") or now_ist().date().isoformat())[:7]
    known, _ = base.sites(user)
    if not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,)):
        return 404, {"error": "not_found", "message": "That person has not opened the tracker yet."}
    if project not in known or not unit:
        return base._bad("Pick the website and what is counted.")
    try:
        qty = float(b.get("qty"))
    except (TypeError, ValueError):
        return base._bad("The monthly target must be a number.")
    if qty <= 0:
        store.write("DELETE FROM task_targets WHERE user_id=? AND project_id=? AND unit=? AND month=?",
                    (who, project, unit, month))
        store.write("DELETE FROM target_splits WHERE user_id=? AND project_id=? AND unit=? AND month=?",
                    (who, project, unit, month))
    else:
        store.write("INSERT INTO task_targets(user_id, project_id, unit, month, qty, set_by) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(user_id, project_id, unit, month) DO UPDATE SET qty=excluded.qty, "
                    "set_by=excluded.set_by", (who, project, unit, month, qty, user.get("name") or ""))
    return plan(user, who, month)


def set_split(user, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    b = body or {}
    who, project, unit = str(b.get("user_id") or ""), str(b.get("project_id") or ""), str(b.get("unit") or "")
    month = str(b.get("month") or "")[:7]
    try:
        ws = _date.fromisoformat(str(b.get("week_start"))[:10])
    except ValueError:
        return base._bad("week_start must be a date.")
    ws -= timedelta(days=ws.weekday())
    if not store.one("SELECT 1 x FROM task_targets WHERE user_id=? AND project_id=? AND unit=? AND month=?",
                     (who, project, unit, month)):
        return base._bad("Set the monthly target first.")
    if b.get("qty") in (None, ""):
        store.write("DELETE FROM target_splits WHERE user_id=? AND project_id=? AND unit=? AND month=? "
                    "AND week_start=?", (who, project, unit, month, ws.isoformat()))
    else:
        try:
            qty = max(0.0, float(b["qty"]))
        except (TypeError, ValueError):
            return base._bad("The week's target must be a number.")
        store.write("INSERT INTO target_splits VALUES (?,?,?,?,?,?) ON CONFLICT(user_id, project_id, unit, month, "
                    "week_start) DO UPDATE SET qty=excluded.qty", (who, project, unit, month, ws.isoformat(), qty))
    return plan(user, who, month)


def templates(user):
    g = _guard(user, admin=True)
    if g:
        return g
    return 200, {"templates": [dict(t, unitLabel=unit_label(t["unit"])) for t in
                               store.rows("SELECT * FROM role_templates ORDER BY role, id")],
                 "units": _unit_choices()}


def put_templates(user, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    items = (body or {}).get("templates")
    if not isinstance(items, list):
        return base._bad("Send the list of templates.")
    conn = store.connect()
    with conn:
        conn.execute("DELETE FROM role_templates")
        for t in items:
            role, unit = str(t.get("role") or "").strip(), str(t.get("unit") or "").strip()
            try:
                q = float(t.get("qty_per_week") or 0)
            except (TypeError, ValueError):
                q = 0
            if role and unit and q > 0:
                conn.execute("INSERT OR REPLACE INTO role_templates(role, unit, qty_per_week) VALUES (?,?,?)",
                             (role, unit, q))
    return templates(user)


def apply_template(user, body):
    """One click: a person gets the role's weekly targets as this month's targets."""
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    b = body or {}
    who, project = str(b.get("user_id") or ""), str(b.get("project_id") or "")
    role = str(b.get("role") or _person(who).get("role") or "seo_lead")
    month = str(b.get("month") or now_ist().date().isoformat())[:7]
    rows = store.rows("SELECT * FROM role_templates WHERE role=?", (role,))
    if not rows:
        return base._bad(f"No template for the role {role}.")
    weeks = len(_workdays(month)) / max(1, len(settings.WORKDAYS))
    for t in rows:
        st, _ = set_target(user, {"user_id": who, "project_id": project, "unit": t["unit"], "month": month,
                                  "qty": round(t["qty_per_week"] * weeks)})
        if st != 200:
            return st, _
    return plan(user, who, month)


def set_leave(user, body, remove=False):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    b = body or {}
    who = str(b.get("user_id") or "")
    if who != "*" and not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,)):
        return 404, {"error": "not_found", "message": "Unknown person (use * for a company holiday)."}
    try:
        d = _date.fromisoformat(str(b.get("date"))[:10]).isoformat()
    except ValueError:
        return base._bad("The date must look like 2026-10-20.")
    if remove:
        store.write("DELETE FROM leave_days WHERE user_id=? AND date=?", (who, d))
    else:
        store.write("INSERT OR REPLACE INTO leave_days(user_id, date, reason) VALUES (?,?,?)",
                    (who, d, str(b.get("reason") or "leave")[:80]))
    return 200, {"userId": who, "date": d, "leave": not remove}


# ------------------------------------------------------------------ RAG for a person (7.4)
def _day_fraction(now):
    h = now.hour + now.minute / 60
    return max(0.0, min(1.0, (h - DAY_START) / (DAY_END - DAY_START)))


def signal(pct, rs):
    if pct is None:
        return "none"
    if pct >= rs["green_min"]:
        return "green"
    return "amber" if pct >= rs["amber_min"] else "red"


def person_rag(user_id, period, now=None, rs=None, on_date=None):
    """Signal for one person over day / week / month. Expected = the planned
    targets up to now (today counts by the share of the working day gone);
    actual = what the sources counted. An overdue task in the period is red."""
    now, rs = now or now_ist(), rs or _rag_settings()
    today = on_date or now.date()
    if period == "day":
        d_from = today
    elif period == "week":
        d_from = today - timedelta(days=today.weekday())
    else:
        d_from = today.replace(day=1)
    person = _person(user_id)
    expected = got = 0.0
    lines = []
    months = {d_from.isoformat()[:7], today.isoformat()[:7]}
    for month in sorted(months):
        for t in store.rows("SELECT * FROM task_targets WHERE user_id=? AND month=?", (str(user_id), month)):
            plan_d = daily_plan(user_id, t["project_id"], t["unit"], month)
            exp = 0.0
            for d in _days(d_from, today):
                q = plan_d.get(d.isoformat(), 0.0)
                exp += q * (_day_fraction(now) if (d == today and on_date is None) else 1.0)
            if exp <= 0:
                continue
            a = actual(t["unit"], person, t["project_id"], d_from.isoformat(), today.isoformat())
            expected += exp
            got += min(a, exp)
            lines.append({"project": t["project_id"], "unit": t["unit"], "unitLabel": unit_label(t["unit"]),
                          "expected": round(exp, 1), "actual": a})
    pct = (got / expected * 100) if expected > 0 else None
    overdue = store.rows(
        "SELECT t.id, t.title FROM tasks t JOIN task_assignees a ON a.task_id=t.id WHERE a.user_id=? "
        "AND t.status NOT IN ('approved','submitted') AND t.due_at < ? AND substr(t.due_at,1,10) >= ?",
        (str(user_id), _fmt(now if on_date is None else datetime.combine(today, datetime.max.time())),
         d_from.isoformat()))
    sig = signal(pct, rs)
    if overdue:
        sig = "red"
    return {"period": period, "signal": sig, "pct": None if pct is None else round(pct),
            "lines": lines, "overdue": overdue, "from": d_from.isoformat(), "to": today.isoformat()}


def my_rag(user, user_id=None):
    g = _guard(user)
    if g:
        return g
    base._seen(user)
    ensure_weekly_idea(user)
    who = str(user_id) if (user_id and base.is_admin(user)) else base.uid(user)
    rs = _rag_settings()
    return 200, {"userId": who, "rag": rs,
                 "signals": {p: person_rag(who, p, rs=rs) for p in ("day", "week", "month")}}


def team_rag(user):
    g = _guard(user, admin=True)
    if g:
        return g
    rs = _rag_settings()
    out = []
    for p in store.rows("SELECT user_id, name, role FROM dt_people ORDER BY lower(name)"):
        if p["role"] in ("owner", "admin"):
            continue
        out.append({"userId": p["user_id"], "name": p["name"],
                    **{per: person_rag(p["user_id"], per, rs=rs)["signal"] for per in ("day", "week", "month")}})
    return 200, {"rows": out, "rag": rs}


def put_rag_settings(user, body):
    g = _guard(user, write=True, admin=True)
    if g:
        return g
    try:
        gm, am = float((body or {}).get("green_min")), float((body or {}).get("amber_min"))
    except (TypeError, ValueError):
        return base._bad("Both thresholds must be numbers.")
    if not 0 < am < gm <= 100:
        return base._bad("Amber must start below green, and both between 1 and 100.")
    store.write("UPDATE rag_settings SET green_min=?, amber_min=? WHERE id=1", (gm, am))
    return 200, _rag_settings()


# ------------------------------------------------------------------ points (7.7)
def _ledger(user_id, name, points, reason, ref_type, ref_id, month):
    store.write("INSERT INTO points_ledger(user_id, user_name, points, reason, ref_type, ref_id, month, created_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id, ref_type, ref_id, reason) DO UPDATE SET "
                "points=excluded.points, month=excluded.month",
                (str(user_id), name or "", float(points), reason, ref_type, str(ref_id), month, store.now_iso()))


def _green_days(user_id, d_from, d_to, cfg):
    """A day is green when the person's targets were met (RAG ≥ green), or —
    with no targets that day — when the Daily Tracker marks target was hit."""
    rs = _rag_settings()
    name = _person(user_id)["name"]
    per = base._per_day(base.totals({str(user_id): name}, d_from.isoformat(), d_to.isoformat(), cfg), str(user_id))
    out = set()
    for d in _days(d_from, d_to):
        r = person_rag(user_id, "day", rs=rs, on_date=d)
        if r["signal"] == "green":
            out.add(d)
        elif r["signal"] == "none":
            x = per.get(d.isoformat())
            if x and x["marks"] >= store.target_for(str(user_id), d.isoformat(), cfg["default_daily_target"]):
                out.add(d)
    return out


def _runs(days):
    """Lengths of consecutive runs, as (end_date, length) for each day."""
    out, run, prev = [], 0, None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        out.append((d, run))
        prev = d
    return out


def sync_points(user_id):
    """Rebuild this person's ledger from its sources (idempotent): approved
    Daily Tracker marks, idea points, 7-green-day streak bonuses. Task points
    are written at approval."""
    uid = str(user_id)
    p = _person(uid)
    cfg = store.get_settings()
    conn = store.connect()
    keep = set()
    for r in store.rows("SELECT id, marks_awarded, log_date FROM daily_logs WHERE user_id=? AND status='approved'",
                        (uid,)):
        _ledger(uid, p["name"], r["marks_awarded"], "work", "daily_log", r["id"], r["log_date"][:7])
        keep.add(("daily_log", str(r["id"]), "work"))
    for i in store.rows("SELECT id, status, created_at, updated_at FROM ideas WHERE user_id=?", (uid,)):
        _ledger(uid, p["name"], IDEA_POINTS["submitted"], "idea_submitted", "idea", i["id"], i["created_at"][:7])
        keep.add(("idea", str(i["id"]), "idea_submitted"))
        if i["status"] in ("in_trial", "worked", "didnt_work"):
            _ledger(uid, p["name"], IDEA_POINTS["trialled"], "idea_trialled", "idea", i["id"], i["updated_at"][:7])
            keep.add(("idea", str(i["id"]), "idea_trialled"))
        if i["status"] == "worked":
            _ledger(uid, p["name"], IDEA_POINTS["worked"], "idea_worked", "idea", i["id"], i["updated_at"][:7])
            keep.add(("idea", str(i["id"]), "idea_worked"))
    today = now_ist().date()
    greens = _green_days(uid, today - timedelta(days=60), today - timedelta(days=1), cfg)
    for d, run in _runs(greens):
        if run % STREAK_RUN == 0:
            _ledger(uid, p["name"], STREAK_POINTS, "streak_7", "streak", d.isoformat(), d.isoformat()[:7])
            keep.add(("streak", d.isoformat(), "streak_7"))
    # A log un-approved or an idea moved back stops paying.
    with conn:
        for r in store.rows("SELECT ref_type, ref_id, reason FROM points_ledger WHERE user_id=? "
                            "AND ref_type IN ('daily_log','idea')", (uid,)):
            if (r["ref_type"], r["ref_id"], r["reason"]) not in keep:
                conn.execute("DELETE FROM points_ledger WHERE user_id=? AND ref_type=? AND ref_id=? AND reason=?",
                             (uid, r["ref_type"], r["ref_id"], r["reason"]))
    return greens


def month_points(user_id, month):
    r = store.one("SELECT COALESCE(SUM(points),0) p FROM points_ledger WHERE user_id=? AND month=?",
                  (str(user_id), month))
    return round(float(r["p"]), 1)


def tiers(user=None, with_notes=False):
    rows = store.rows("SELECT id, name, min_points, bonus_note FROM reward_tiers ORDER BY min_points")
    if not with_notes:
        for r in rows:
            r.pop("bonus_note", None)
    return rows


def tier_for(points, rows):
    cur, nxt = None, None
    for t in rows:
        if points >= t["min_points"]:
            cur = t
        elif nxt is None:
            nxt = t
    return cur, nxt


def get_tiers(user):
    g = _guard(user)
    if g:
        return g
    return 200, {"tiers": tiers(with_notes=base.is_admin(user)), "canEdit": is_super(user)}


def put_tiers(user, body):
    g = _guard(user, write=True, superuser=True)
    if g:
        return g
    items = (body or {}).get("tiers")
    if not isinstance(items, list) or not items:
        return base._bad("Send the tiers.")
    clean = []
    for t in items:
        name = str(t.get("name") or "").strip()[:30]
        try:
            mp = float(t.get("min_points"))
        except (TypeError, ValueError):
            return base._bad(f"{name or 'A tier'}: points must be a number.")
        if not name or mp < 0:
            return base._bad("Every tier needs a name and points ≥ 0.")
        clean.append((name, mp, str(t.get("bonus_note") or "")[:200]))
    if len({c[0].lower() for c in clean}) != len(clean):
        return base._bad("Tier names must differ.")
    conn = store.connect()
    with conn:
        conn.execute("DELETE FROM reward_tiers")
        conn.executemany("INSERT INTO reward_tiers(name, min_points, bonus_note) VALUES (?,?,?)", clean)
    return get_tiers(user)


def put_mirror_settings(user, body):
    g = _guard(user, write=True, superuser=True)
    if g:
        return g
    cfg = store.get_settings()
    cfg["show_rank"] = bool((body or {}).get("show_rank"))
    store.put_settings(cfg, user.get("name") or "")
    return 200, {"show_rank": cfg["show_rank"]}


# ------------------------------------------------------------------ Mirror (7.5)
def badges(user_id, month, greens):
    out = []
    best = max([r for _, r in _runs(greens)] or [0])
    if best >= 7:
        out.append({"key": "streak7", "label": "Streak 7"})
    if best >= 30:
        out.append({"key": "streak30", "label": "Streak 30"})
    y, m = int(month[:4]), int(month[5:7])
    last = f"{month}-{calendar.monthrange(y, m)[1]:02d}T23:59"
    if month < now_ist().date().isoformat()[:7]:
        tasks_m = store.rows("SELECT t.status, t.due_at, t.submitted_at FROM tasks t JOIN task_assignees a "
                             "ON a.task_id=t.id WHERE a.user_id=? AND substr(t.due_at,1,7)=?", (str(user_id), month))
        if tasks_m and all(t["submitted_at"] and t["submitted_at"] <= t["due_at"] for t in tasks_m):
            out.append({"key": "zero_overdue", "label": "Zero overdue month"})
    q = _quality_items(user_id, f"{month}-01", last[:10])
    if len(q) >= 5 and sum(x["q"] for x in q) / len(q) >= 4.5:
        out.append({"key": "top_quality", "label": "Top quality"})
    if store.one("SELECT 1 x FROM user_badges WHERE user_id=? AND month=?", (str(user_id), month)):
        out.append({"key": "idea_winner", "label": "Idea of the Month"})
    return out


def _quality_items(user_id, d_from, d_to):
    out = [{"q": r["quality"], "type": r["name"]} for r in store.rows(
        "SELECT l.quality, w.name FROM daily_logs l JOIN work_types w ON w.id=l.work_type_id WHERE l.user_id=? "
        "AND l.quality IS NOT NULL AND l.status IN ('approved','needs_fix','rejected') AND l.log_date BETWEEN ? AND ?",
        (str(user_id), d_from, d_to))]
    out += [{"q": r["quality"], "type": unit_label(r["unit"])} for r in store.rows(
        "SELECT t.quality, t.unit FROM tasks t JOIN task_assignees a ON a.task_id=t.id WHERE a.user_id=? "
        "AND t.quality IS NOT NULL AND substr(t.approved_at,1,10) BETWEEN ? AND ?", (str(user_id), d_from, d_to))]
    return out


def mirror(user, user_id=None, month=None):
    g = _guard(user)
    if g:
        return g
    base._seen(user)
    admin = base.is_admin(user)
    who = str(user_id) if (user_id and admin) else base.uid(user)
    month = (month or now_ist().date().isoformat())[:7]
    y, m = int(month[:4]), int(month[5:7])
    m_from, m_to = f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}"
    rs = _rag_settings()
    cfg = store.get_settings()
    greens = sync_points(who)
    today = now_ist().date()
    history = []
    for d in _days(today - timedelta(days=29), today):
        r = person_rag(who, "day", rs=rs, on_date=d if d < today else None)
        history.append({"date": d.isoformat(), "signal": "green" if d in greens and r["signal"] == "none"
                        else r["signal"]})
    done = store.rows("SELECT t.submitted_at, t.due_at FROM tasks t JOIN task_assignees a ON a.task_id=t.id "
                      "WHERE a.user_id=? AND t.kind='task' AND (t.status IN ('approved','submitted') OR t.due_at < ?) "
                      "AND substr(t.due_at,1,7)=?", (who, _fmt(now_ist()), month))
    logs = store.rows("SELECT late FROM daily_logs WHERE user_id=? AND substr(log_date,1,7)=? "
                      "AND status != 'submitted'", (who, month))
    on_time_n = sum(1 for t in done if t["submitted_at"] and t["submitted_at"] <= t["due_at"]) + \
        sum(1 for x in logs if not x["late"])
    total = len(done) + len(logs)
    q = _quality_items(who, m_from, m_to)
    by_type = {}
    for x in q:
        by_type.setdefault(x["type"], []).append(x["q"])
    ranked = sorted(((k, round(sum(v) / len(v), 2), len(v)) for k, v in by_type.items()), key=lambda r: -r[1])
    rework = store.one("SELECT COALESCE(SUM(t.rework),0) n FROM tasks t JOIN task_assignees a ON a.task_id=t.id "
                       "WHERE a.user_id=? AND substr(t.due_at,1,7)=?", (who, month))["n"] + \
        store.one("SELECT COALESCE(SUM(rework),0) n FROM daily_logs WHERE user_id=? AND substr(log_date,1,7)=?",
                  (who, month))["n"]
    pts = month_points(who, month)
    trows = tiers(with_notes=True)
    cur, nxt = tier_for(pts, trows)
    gap = round(nxt["min_points"] - pts, 1) if nxt else 0
    ways = []
    if nxt:
        for name in ("Blog article published", "Guest post"):
            w = store.one("SELECT base_marks FROM work_types WHERE name=? AND active=1", (name,))
            if w and w["base_marks"] > 0:
                ways.append(f"{math.ceil(gap / w['base_marks'])} more approved “{name}” (quality 3) = {nxt['name']}")
        ways.append(f"1 idea marked Worked = +{IDEA_POINTS['worked']} points"
                    + (f" (enough for {nxt['name']})" if gap <= IDEA_POINTS["worked"] else ""))
        open_t = store.rows("SELECT t.id, t.title, t.marks FROM tasks t JOIN task_assignees a ON a.task_id=t.id "
                            "WHERE a.user_id=? AND t.status NOT IN ('approved') AND t.marks > 0 "
                            "ORDER BY t.marks DESC LIMIT 3", (who,))
        for t in open_t:
            ways.append(f"Finish “{t['title']}” on time = about {round(t['marks'] * (1 + ON_TIME_BONUS))} points")
    show_rank = cfg.get("show_rank", True)
    rank = None
    if show_rank or admin:
        board = sorted(((month_points(p["user_id"], month), p["user_id"]) for p in
                        store.rows("SELECT user_id FROM dt_people WHERE role NOT IN ('owner','admin')")), reverse=True)
        ids = [b[1] for b in board]
        rank = {"rank": ids.index(who) + 1, "of": len(ids)} if who in ids else None
    self_or_admin = admin or who == base.uid(user)
    return 200, {
        "userId": who, "name": _person(who)["name"], "month": month,
        "signals": {p: person_rag(who, p, rs=rs) for p in ("day", "week", "month")},
        "history": history,
        "onTimePct": round(100 * on_time_n / total) if total else None,
        "qualityAvg": round(sum(x["q"] for x in q) / len(q), 2) if q else None,
        "rework": int(rework),
        "points": pts,
        "tier": ({"name": cur["name"], "min_points": cur["min_points"],
                  **({"bonus_note": cur["bonus_note"]} if self_or_admin else {})} if cur else None),
        "nextTier": ({"name": nxt["name"], "min_points": nxt["min_points"], "gap": gap,
                      **({"bonus_note": nxt["bonus_note"]} if self_or_admin else {})} if nxt else None),
        "ways": ways[:5],
        "rank": rank, "showRank": show_rank,
        "strengths": [{"type": k, "avg": a, "n": n} for k, a, n in ranked if n >= 2][:3],
        "gaps": [{"type": k, "avg": a, "n": n} for k, a, n in reversed(ranked) if n >= 2][:3],
        "badges": badges(who, month, greens),
        "ledger": store.rows("SELECT points, reason, ref_type, ref_id, created_at FROM points_ledger "
                             "WHERE user_id=? AND month=? ORDER BY id DESC LIMIT 50", (who, month)),
    }


# ------------------------------------------------------------------ monthly rewards (7.7)
def rewards(user, month=None):
    g = _guard(user, admin=True)
    if g:
        return g
    month = (month or now_ist().date().isoformat())[:7]
    trows = tiers(with_notes=True)
    approved = {r["user_id"]: r for r in store.rows("SELECT * FROM reward_months WHERE month=?", (month,))}
    out = []
    for p in store.rows("SELECT user_id, name, role FROM dt_people ORDER BY lower(name)"):
        if p["role"] in ("owner", "admin"):
            continue
        sync_points(p["user_id"])
        pts = month_points(p["user_id"], month)
        cur, _ = tier_for(pts, trows)
        out.append({"userId": p["user_id"], "name": p["name"], "points": pts,
                    "tier": cur["name"] if cur else "", "bonusNote": cur["bonus_note"] if cur else "",
                    "approved": approved.get(p["user_id"])})
    return 200, {"month": month, "rows": out, "canApprove": is_super(user)}


def approve_rewards(user, body):
    g = _guard(user, write=True, superuser=True)
    if g:
        return g
    month = str((body or {}).get("month") or "")[:7]
    if len(month) != 7:
        return base._bad("Which month?")
    _, data = rewards(user, month)
    now = store.now_iso()
    for r in data["rows"]:
        store.write("INSERT OR REPLACE INTO reward_months(month, user_id, user_name, points, tier, approved_by, "
                    "approved_at) VALUES (?,?,?,?,?,?,?)",
                    (month, r["userId"], r["name"], r["points"], r["tier"], user.get("name") or "", now))
    return rewards(user, month)


def rewards_csv(user, month=None):
    st, data = rewards(user, month)
    if st != 200:
        return st, data
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Month", "Person", "Points", "Tier", "Bonus (from tier settings)", "Approved by", "Approved at"])
    for r in data["rows"]:
        a = r["approved"] or {}
        w.writerow([data["month"], r["name"], r["points"], a.get("tier", r["tier"]), r["bonusNote"],
                    a.get("approved_by", ""), a.get("approved_at", "")])
    return 200, buf.getvalue()
