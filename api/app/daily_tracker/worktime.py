"""Tasks v2 — the task timer, the 15-minute proof and road blockers (Step 2).

The server is the truth. Every action closes or opens a work_intervals row and
writes a task_events row in one transaction; the browser only displays.

  * one running task per person: starting another pauses the first
  * an interval left open on an earlier day blocks everything until the person
    sets its end time (never invented by the server; v3: closes by itself at 4 AM)
  * worked time = work intervals, merged (never double-counted), cut into
    15-minute slots; a slot counts only once it has proof
  * yesterday is locked: proof only for today's slots
  * road blocker: the watch stops at once, a task_holds row waits for Jai when
    the category says so, and the person gets their next task suggested
  * v3 (FEATURE_TASKS_V3): "Start my day" clocks in (work_days); a task starts
    only inside a started day. A work day runs 4 AM to 4 AM IST; a day nobody ended
    closes by itself then (_autoclose), and a forgotten running timer counts nothing. No proof at all (Jai, 27 Oct): timer time
    counts as it runs, Done needs no link. A dependency stop picks a reason
    from block_reasons and offers Jai's daily tasks (daily_routines) to jump to.
    Break / Lunch / Thinking / Waiting are one tap (take_break); the same tap resumes

Times are stored UTC ISO; days and slots are IST (store.IST).
"""
import json
import sqlite3
from datetime import date as _date, datetime, timedelta, timezone
from urllib.parse import urlparse

from . import service as base, store, taskmgr
from .config import settings

IST = store.IST
ERR_OFF = (404, {"error": "disabled", "message": "Tasks v2 is not switched on."})
ERR_OFF_V3 = (404, {"error": "disabled", "message": "The Start my day flow is not switched on."})
ERR_SUPER = (403, {"error": "forbidden", "message": "Only Jai can decide that."})
WORKABLE = ("todo", "paused", "in_progress")
DONE = ("submitted", "accepted", "cancelled")
PRIO = {"P1": 1, "P2": 2, "P3": 3}
COUNTS = ("work", "thinking")          # interval types that are effective work
BREAKS = ("break", "lunch", "thinking", "waiting")  # v3 one-tap buttons; thinking still counts as work
NOTE_MAX = 300


class _Taken(Exception):
    """Someone else picked the pool task a moment earlier."""


# ------------------------------------------------------------------ helpers
def _guard(user, write=False, superuser=False, now=None):
    if not settings.TASKS_V2:
        return ERR_OFF
    if not user:
        return base.ERR_AUTH
    _autoclose(base.uid(user), _now(now))
    if superuser and not taskmgr.is_super(user):
        return ERR_SUPER
    if write and taskmgr.is_viewer(user):
        return taskmgr.ERR_VIEWER
    if write and settings.READ_ONLY:
        return base.ERR_FROZEN
    return None


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _ist(s):
    return datetime.fromisoformat(s).astimezone(IST)


def _off():
    """v3: a work day runs from day_starts_hour (4 AM IST) to 4 AM next day, so late-night work stays on it."""
    return timedelta(hours=work_settings()["day_starts_hour"]) if settings.TASKS_V3 else timedelta(0)


def work_date(dt):
    return (dt.astimezone(IST) - _off()).date()


def _day_start(day):
    return datetime.fromisoformat(str(day)).replace(tzinfo=IST) + _off()


def cycle_of(day):
    """The work month a date belongs to: 26th..25th (month_closes_day), named by the month it closes in."""
    close = work_settings()["month_closes_day"]
    y, m = (day.year + (day.month == 12), day.month % 12 + 1) if day.day > close else (day.year, day.month)
    return f"{y}-{m:02d}"


def cycle_bounds(cycle):
    """(first day, last day) of a work month, e.g. '2026-11' -> 2026-10-26, 2026-11-25."""
    close = work_settings()["month_closes_day"]
    y, m = map(int, cycle.split("-"))
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return _date(py, pm, close) + timedelta(days=1), _date(y, m, close)


def _autoclose(user_id, now):
    """v3: at 4 AM a day nobody ended closes by itself. A timer left running stops where it started
    (the forgotten run counts nothing: never guessed); the day ends at the last thing done."""
    if not settings.TASKS_V3 or settings.READ_ONLY:
        return
    today = work_date(now)
    iv = _open(user_id)
    iv = iv if iv and work_date(_ist(iv["start_ts"])) < today else None
    days = store.rows("SELECT * FROM work_days WHERE user_id=? AND date<? AND end_at IS NULL", (user_id, today.isoformat()))
    if not iv and not days:
        return
    conn = store.connect()
    with conn:
        if iv:
            conn.execute("UPDATE work_intervals SET end_ts=start_ts WHERE id=?", (iv["id"],))
            t = _task(iv["task_id"]) if iv["task_id"] else None
            if t and t["status"] == "in_progress":
                _set_status(conn, t, "paused", user_id, "auto_stop", now, "forgot to stop; not counted")
        for d in days:
            last = conn.execute("SELECT MAX(COALESCE(end_ts, start_ts)) t FROM work_intervals WHERE user_id=? "
                                "AND start_ts>=? AND start_ts<?", (user_id, _iso(_day_start(d["date"])),
                                _iso(_day_start(_date.fromisoformat(d["date"]) + timedelta(days=1))))).fetchone()["t"]
            end = max([d["start_at"]] + ([_iso(_ist(last))] if last else []))
            conn.execute("UPDATE work_days SET end_at=?, end_source='auto' WHERE id=?", (end, d["id"]))
            _event(conn, user_id, None, "day_end_auto", now, reason=f"{d['date']} not ended; closed at {_ist(end):%H:%M}")


def _slot_key(dt):
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M")


def work_settings():
    r = store.one("SELECT value FROM work_settings ORDER BY id DESC LIMIT 1")
    out = dict(store.DEFAULT_WORK_SETTINGS)
    out.update(json.loads(r["value"]) if r else {})
    return out


def week_on(day):
    """The weekly hours in force on a date: the latest change that started by then, else the settings."""
    r = store.one("SELECT week FROM week_hours WHERE effective_from<=? ORDER BY effective_from DESC, id DESC LIMIT 1",
                  (str(day),))
    return json.loads(r["week"]) if r else work_settings()["week_hours"]


def user_target(user_id, day):
    """A person's hours for a day: the day's target less their leave that day (v3)."""
    if not settings.TASKS_V3:
        return target_hours(day)
    from . import leave
    return max(0.0, target_hours(day) - leave.excused_hours(user_id, day))


def target_hours(day):
    """The day's target: Jai's hours for that date if set, else the weekly hours in force that day."""
    o = store.one("SELECT hours FROM day_hours WHERE date=? ORDER BY id DESC LIMIT 1", (day,))
    if o and o["hours"] is not None:
        return float(o["hours"])
    return float(week_on(day)[_date.fromisoformat(day).weekday()])


def _event(conn, user_id, task_id, kind, now, prev="", new="", reason="", actor=""):
    conn.execute("INSERT INTO task_events(user_id, task_id, event_type, server_ts, prev_state, new_state, "
                 "reason, source, actor_id) VALUES (?,?,?,?,?,?,?,?,?)",
                 (user_id, task_id, kind, _iso(now), prev, new, reason[:NOTE_MAX], "web", actor or user_id))


def _set_status(conn, t, new, user_id, kind, now, reason="", actor=""):
    conn.execute("UPDATE work_tasks SET status=?, updated_at=? WHERE id=?", (new, _iso(now), t["id"]))
    _event(conn, user_id, t["id"], kind, now, t["status"], new, reason, actor)


def _task(task_id):
    return store.one("SELECT * FROM work_tasks WHERE id=?", (task_id,))


def _open(user_id):
    return store.one("SELECT * FROM work_intervals WHERE user_id=? AND end_ts IS NULL", (user_id,))


def _stale(iv, now):
    return bool(iv) and work_date(_ist(iv["start_ts"])) < work_date(now)


def _close(conn, iv, now, user_id, kind="pause", reason=""):
    """Close the open interval and pause its task (if it was the running one)."""
    conn.execute("UPDATE work_intervals SET end_ts=? WHERE id=?", (_iso(now), iv["id"]))
    t = _task(iv["task_id"]) if iv["task_id"] else None
    if t and t["status"] == "in_progress":
        _set_status(conn, t, "paused", user_id, kind, now, reason)


def team():
    """The people Jai manages: everyone in the tracker except the superusers themselves."""
    return [p for p in store.rows("SELECT user_id, name, email FROM dt_people ORDER BY name")
            if p["email"].strip().lower() not in settings.SUPERUSERS]


def _add_workdays(day, n, workdays):
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() in workdays:
            n -= 1
    return day


def _categories(active_only=True):
    out = []
    for c in store.rows("SELECT * FROM task_categories" + (" WHERE active=1" if active_only else "")
                        + " ORDER BY sort_order, id"):
        c["fields"] = json.loads(c["fields"] or "[]")
        out.append(c)
    return out


def _public(t, cats=None):
    cats = cats or {c["id"]: c for c in _categories(False)}
    c = cats.get(t["category_id"]) or {}
    return {**t, "details": json.loads(t["details"] or "{}"), "category": c.get("name", ""),
            "pool": bool(t["pool"])}


def _day(user_id, day):
    return store.one("SELECT * FROM work_days WHERE user_id=? AND date=?", (user_id, day))


def _unended(user_id, today):
    """An earlier day the person never ended (the oldest first)."""
    return store.one("SELECT * FROM work_days WHERE user_id=? AND date<? AND end_at IS NULL ORDER BY date LIMIT 1",
                     (user_id, today))


def _end_time(body):
    """The person's own stop time, IST 'YYYY-MM-DDTHH:MM'; None if it doesn't parse."""
    try:
        return datetime.fromisoformat(str((body or {}).get("end"))).replace(tzinfo=IST)
    except ValueError:
        return None


# ------------------------------------------------------------------ time math
def _spans(user_id, day, now):
    """[(start, end, task_id)] of effective work on that IST day, clipped to the day."""
    d0 = _day_start(day)
    d1 = d0 + timedelta(days=1)
    out = []
    for iv in store.rows("SELECT * FROM work_intervals WHERE user_id=? AND type IN (?,?) AND start_ts < ? "
                         "AND (end_ts IS NULL OR end_ts > ?) ORDER BY start_ts",
                         (user_id, *COUNTS, _iso(d1), _iso(d0))):
        a = max(_ist(iv["start_ts"]), d0)
        b = min(_ist(iv["end_ts"]) if iv["end_ts"] else now.astimezone(IST), d1)
        if b > a:
            out.append((a, b, iv["task_id"]))
    return out


def _cut(a, b, slot_min):
    """Yield (slot key, minutes) for the span a..b cut on slot boundaries."""
    s = a.replace(minute=a.minute - a.minute % slot_min, second=0, microsecond=0)
    while s < b:
        e = s + timedelta(minutes=slot_min)
        yield _slot_key(s), (min(b, e) - max(a, s)).total_seconds() / 60
        s = e


def day_slots(user_id, day, now=None, slot_min=None):
    """{slot 'YYYY-MM-DDTHH:MM': {'minutes', 'task_id'}}. Minutes come from the
    intervals MERGED, so the same minute never counts twice; the task is the one
    with the most time in that slot."""
    now = _now(now)
    slot_min = slot_min or int(work_settings()["slot_minutes"])
    spans = sorted(_spans(user_id, day, now), key=lambda x: x[:2])
    merged = []
    for a, b, _t in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = {}
    for a, b in merged:
        for k, mins in _cut(a, b, slot_min):
            out.setdefault(k, {"minutes": 0.0, "task_id": None})["minutes"] += mins
    per_task = {}
    for a, b, tid in spans:
        for k, mins in _cut(a, b, slot_min):
            per_task.setdefault(k, {}).setdefault(tid, 0.0)
            per_task[k][tid] += mins
    for k, by in per_task.items():
        out[k]["task_id"] = max(by, key=by.get)
    return out


def day_work(user_id, day, now=None):
    """Worked minutes (all), proven minutes (count toward targets) and the slots still needing proof."""
    now = _now(now)
    slots = day_slots(user_id, day, now)
    proven = set(slots) if settings.TASKS_V3 else {r["slot_start"] for r in store.rows(
        "SELECT slot_start FROM work_slots WHERE user_id=? AND slot_start LIKE ?", (user_id, day + "%"))}
    over = 0.0
    if settings.TASKS_V3:  # Thinking beyond the daily cap doesn't count
        over = max(0.0, _break_minutes(user_id, day, now)["thinking"] - work_settings()["thinking_cap_minutes"])
    return {"workedMinutes": round(sum(s["minutes"] for s in slots.values()), 1),
            "provenMinutes": round(sum(s["minutes"] for k, s in slots.items() if k in proven) - over, 1),
            "needProof": [{"slot": k, "minutes": round(s["minutes"], 1), "taskId": s["task_id"]}
                          for k, s in sorted(slots.items()) if k not in proven]}


def suggestions(user_id, exclude=None):
    """What to do next: own workable tasks (priority, then due date), then the Pool."""
    key = lambda t: (PRIO.get(t["priority"], 9), t["due_date"] or "9999-99-99", t["id"])  # noqa: E731
    own = [t for t in store.rows("SELECT * FROM work_tasks WHERE assigned_to=? AND status IN (?,?,?)",
                                 (user_id, *WORKABLE)) if t["id"] != exclude]
    pool = store.rows("SELECT * FROM work_tasks WHERE pool=1 AND status='pool'")
    cats = {c["id"]: c for c in _categories(False)}
    return [_public(t, cats) for t in sorted(own, key=key) + sorted(pool, key=key)][:5]


# ------------------------------------------------------------------ read
def state(user, now=None):
    g = _guard(user, now=now)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    today = work_date(now).isoformat()
    cfg = work_settings()
    cats = {c["id"]: c for c in _categories(False)}
    iv = _open(me)
    mine = store.rows("SELECT * FROM work_tasks WHERE assigned_to=? AND status NOT IN (?,?,?) "
                      "ORDER BY id DESC", (me, *DONE))
    pool = store.rows("SELECT * FROM work_tasks WHERE pool=1 AND status='pool' ORDER BY id DESC")
    holds = store.rows("SELECT * FROM task_holds WHERE user_id=? AND (end_ts IS NULL OR status='pending') "
                       "ORDER BY id DESC", (me,))
    approve = (store.rows("SELECT h.*, t.title FROM task_holds h JOIN work_tasks t ON t.id=h.task_id "
                          "WHERE h.status='pending' ORDER BY h.id") if taskmgr.is_super(user) else [])
    work = day_work(me, today, now)
    target = user_target(me, today) * 60
    signal = cfg["signal"]
    return 200, {
        "now": _iso(now), "today": today,
        "running": iv and {"interval": iv, "task": iv["task_id"] and _public(_task(iv["task_id"]), cats),
                           "stale": _stale(iv, now)},
        "tasks": [_public(t, cats) for t in mine], "pool": [_public(t, cats) for t in pool],
        "holds": holds, "approve": approve,
        "categories": [c for c in cats.values() if c["active"]],
        "people": store.rows("SELECT user_id, name FROM dt_people ORDER BY name"),
        "work": {**work, "targetMinutes": target, "leftMinutes": max(0.0, target - work["provenMinutes"])},
        "settings": {"slotMinutes": cfg["slot_minutes"], "dailyTargetHours": target / 60,
                     "dayLateAfter": cfg["day_late_after"], "greenMin": signal["green_min"],
                     "amberMin": signal["amber_min"], "thinkingCap": cfg["thinking_cap_minutes"]},
        "tasksDone": store.one("SELECT COUNT(*) c FROM task_events WHERE user_id=? AND event_type='complete' "
                               "AND server_ts >= ?", (me, _iso(_day_start(today))))["c"],
        "hoursChanges": [{**r, "week": json.loads(r["week"])} for r in store.rows(
            "SELECT week, effective_from FROM week_hours WHERE effective_from>? ORDER BY effective_from, id", (today,))],
        "hours": {"week": week_on(today), "days": store.rows(
            "SELECT date, hours, note FROM day_hours d WHERE id=(SELECT MAX(id) FROM day_hours WHERE date=d.date) "
            "AND date>=? AND hours IS NOT NULL ORDER BY date LIMIT 60", (today,))} if taskmgr.is_super(user) else None,
        "isSuperuser": taskmgr.is_super(user),
        "credit": month_credit(me, cycle_of(work_date(now)), now) if settings.TASKS_V3 else None,
        "teamCredits": [{**p, **month_credit(p["user_id"], cycle_of(work_date(now)), now),
                         "allowanceHours": allowance_hours(p["user_id"])}
                        for p in team()]
        if settings.TASKS_V3 and taskmgr.is_super(user) else [],
        "allowanceAll": allowance_hours("*"),
        **(_game(me, user, now, today) if settings.TASKS_V3 else {}),
        "teamDays": store.rows("SELECT d.user_id, p.name, d.start_at, d.end_at, d.status, d.end_source FROM work_days d "
                               "LEFT JOIN dt_people p ON p.user_id=d.user_id WHERE d.date=? ORDER BY p.name", (today,))
        if taskmgr.is_super(user) else [],
        "dayFlow": settings.TASKS_V3, "day": _day(me, today),
        "blockReasons": cfg["block_reasons"], "routines": routines(me),
        "breaks": {"used": _break_minutes(me, today, now),
                   "limit": {"break": cfg["breaks"]["short_minutes"] * cfg["breaks"]["short_per_day"],
                             "lunch": cfg["breaks"]["lunch_minutes"] * cfg["breaks"]["lunch_per_day"]}},
        "routinesAll": _routines_public(store.rows("SELECT * FROM daily_routines ORDER BY active DESC, id"))
        if taskmgr.is_super(user) else [],
    }


# ------------------------------------------------------------------ tasks
def _details(b):
    """(category, its required fields filled in) or (None, error answer)."""
    cat = next((c for c in _categories() if c["id"] == b.get("category_id")), None)
    if not cat:
        return None, base._bad("Pick a category.")
    given = b.get("details") or {}
    details = {}
    for f in cat["fields"]:
        v = str(given.get(f["key"]) or "").strip()
        if not v or (f["type"] == "choice" and v not in f["options"]):
            return None, base._bad(f"{cat['name']}: fill in “{f['label']}”.")
        details[f["key"]] = v[:NOTE_MAX]
    return cat, details


def create_task(user, body, now=None, routine_id=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    b = body or {}
    me = base.uid(user)
    title = str(b.get("title") or "").strip()
    if not 3 <= len(title) <= 200:
        return base._bad("Give the task a title (3 to 200 characters).")
    cat, details = _details(b)
    if not cat:
        return details
    if routine_id:
        details["routine_id"] = routine_id
    prio = b.get("priority") or "P2"
    if prio not in PRIO:
        return base._bad("Priority is P1, P2 or P3.")
    try:
        est = int(b.get("estimate_min") or 0)
        due = _date.fromisoformat(b["due_date"]).isoformat() if b.get("due_date") else None
    except (ValueError, TypeError):
        return base._bad("Estimate is minutes; the due date looks like 2026-10-27.")
    if not 0 <= est <= 7 * 24 * 60:
        return base._bad("The estimate must be between 0 and 10080 minutes.")
    if b.get("complexity"):  # v3 Step 6: points multiplier, kept with the task's details
        if b["complexity"] not in ("Easy", "Medium", "Hard"):
            return base._bad("Complexity is Easy, Medium or Hard.")
        details["complexity"] = b["complexity"]
    # Admins may assign to someone or post to the Pool; everyone else adds their own.
    target = str(b.get("assign_to") or me) if base.is_admin(user) else me
    pool = target == "pool"
    if not pool and target != me and not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (target,)):
        return 404, {"error": "not_found", "message": "Unknown person."}
    if cat["deadline_workdays"] and not pool:
        due = _add_workdays(now.astimezone(IST).date(), cat["deadline_workdays"],
                            work_settings()["working_days"]).isoformat()
    conn = store.connect()
    with conn:
        cur = conn.execute(
            "INSERT INTO work_tasks(title, description, category_id, project_id, domain, priority, estimate_min, "
            "status, pool, assigned_to, due_date, details, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, str(b.get("description") or "")[:2000], cat["id"], str(b.get("project_id") or ""),
             str(b.get("domain") or details.get("website") or ""), prio, est, "pool" if pool else "todo",
             int(pool), None if pool else target, due, json.dumps(details), me, _iso(now), _iso(now)))
        _event(conn, me if pool else target, cur.lastrowid, "create", now, "", "pool" if pool else "todo",
               actor=me)
    return 201, {"task": _public(_task(cur.lastrowid))}


def start(user, task_id, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    t = _task(task_id)
    if not t:
        return 404, {"error": "not_found", "message": "No such task."}
    picking = t["pool"] and t["status"] == "pool"
    if not picking and t["assigned_to"] != me:
        return 403, {"error": "forbidden", "message": "That task belongs to someone else."}
    if not picking and t["status"] not in WORKABLE:
        return 409, {"error": "not_workable", "message": f"This task is {t['status']}."}
    if settings.TASKS_V3:
        d = _day(me, work_date(now).isoformat())
        if not d or d["end_at"]:
            return 409, {"error": "day_not_started" if not d else "day_ended",
                         "message": "Press Start my day first." if not d else "You ended your day already."}
    iv = _open(me)
    if _stale(iv, now):
        return 409, {"error": "open_session",
                     "message": "You left a timer running on an earlier day. Set when you stopped first."}
    if iv and iv["task_id"] == task_id and iv["type"] == "work":
        return state(user, now)
    conn = store.connect()
    try:
        _start(conn, me, t, task_id, iv, picking, now)
    except _Taken:
        return 409, {"error": "taken", "message": "Someone picked that task a moment ago."}
    return state(user, now)


def _start(conn, me, t, task_id, iv, picking, now):
    with conn:
        if iv:
            _close(conn, iv, now, me, "auto_pause", "switched task")
        if picking:
            cat = store.one("SELECT deadline_workdays FROM task_categories WHERE id=?", (t["category_id"],)) or {}
            due = t["due_date"]
            if cat.get("deadline_workdays"):
                due = _add_workdays(now.astimezone(IST).date(), cat["deadline_workdays"],
                                    work_settings()["working_days"]).isoformat()
            # The WHERE re-checks the pool state: two people clicking Pick at once, only one wins.
            cur = conn.execute("UPDATE work_tasks SET pool=0, status='todo', assigned_to=?, picked_by=?, "
                               "picked_at=?, due_date=?, updated_at=? WHERE id=? AND pool=1 AND status='pool'",
                               (me, me, _iso(now), due, _iso(now), task_id))
            if cur.rowcount != 1:
                raise _Taken()
            _event(conn, me, task_id, "pick", now, "pool", "todo")
            t = _task(task_id)
        conn.execute("INSERT INTO work_intervals(user_id, task_id, type, start_ts, created_at) VALUES (?,?,?,?,?)",
                     (me, task_id, "work", _iso(now), _iso(now)))
        _set_status(conn, t, "in_progress", me, "start", now)


def pause(user, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    iv = _open(me)
    if not iv:
        return state(user, now)
    if _stale(iv, now):
        return 409, {"error": "open_session", "message": "Set when you stopped that earlier timer first."}
    conn = store.connect()
    with conn:
        _close(conn, iv, now, me)
    return state(user, now)


def take_break(user, body, now=None):
    """v3 one-tap Break / Lunch / Thinking / Waiting. The running task pauses and is
    kept on the break interval; the same tap again resumes it. Another kind switches."""
    g = _guard_v3(user, now)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    kind = str((body or {}).get("type") or "")
    if kind not in BREAKS:
        return base._bad("Pick Break, Lunch, Thinking or Waiting.")
    d = _day(me, work_date(now).isoformat())
    if not d or d["end_at"]:
        return 409, {"error": "day_not_started" if not d else "day_ended",
                     "message": "Press Start my day first." if not d else "You ended your day already."}
    iv = _open(me)
    if _stale(iv, now):
        return 409, {"error": "open_session", "message": "Set when you stopped that earlier timer first."}
    t = _task(iv["task_id"]) if iv and iv["task_id"] else None
    conn = store.connect()
    if iv and iv["type"] == kind:  # tap again = resume the task it paused
        if t and t["status"] in WORKABLE:
            _start(conn, me, t, t["id"], iv, False, now)
        else:
            with conn:
                _close(conn, iv, now, me)
        return state(user, now)
    with conn:
        if iv:
            _close(conn, iv, now, me, "auto_pause", kind)
        conn.execute("INSERT INTO work_intervals(user_id, task_id, type, start_ts, created_at) VALUES (?,?,?,?,?)",
                     (me, t["id"] if t else None, kind, _iso(now), _iso(now)))
    return state(user, now)


def _game(me, user, now, today):
    """v3 Step 6 + the month bar: points, streak, badges, leaderboard, Jai's accept queue."""
    from . import game
    cfg = work_settings()
    first = store.one("SELECT MIN(date) d FROM work_days WHERE user_id=?", (me,))["d"]
    cycle = cycle_of(work_date(now))
    m0, m1 = cycle_bounds(cycle)
    d, goal = max(m0, _date.fromisoformat(first)) if first else work_date(now), 0.0
    while d <= m1:
        goal += user_target(me, d.isoformat()) * 60
        d += timedelta(days=1)
    c = month_credit(me, cycle, now)
    idea = store.one("SELECT COUNT(*) c FROM big_ideas WHERE user_id=? AND month=? AND status!='repeat'",
                     (me, cycle))["c"] >= cfg["ideas_required"]
    from . import leave
    return {"game": game.summary(me, now), "leaderboard": game.leaderboard(now),
            "leave": leave.summary(me, cycle),
            "teamLeave": [{"user_id": p["user_id"], "name": p["name"], **leave.summary(p["user_id"], cycle)} for p in team()]
            if taskmgr.is_super(user) else [],
            "leaveAll": leave.policy("*"),
            "toReview": game.to_review() if taskmgr.is_super(user) else [],
            "chunks": cfg["chunks"], "pointsPerHour": cfg["points_per_hour"],
            "complexity": cfg["complexity_multiplier"],
            "monthGoal": {"month": cycle, "to": m1.isoformat(), "targetMinutes": goal, "ideaGiven": idea,
                          "workedMinutes": round(c["workedMinutes"] + day_work(me, today, now)["provenMinutes"], 1)}}


def _break_minutes(user_id, day, now):
    """{type: minutes} of Break / Lunch / Thinking / Waiting started that IST day."""
    d0 = _day_start(day)
    out = dict.fromkeys(BREAKS, 0.0)
    for iv in store.rows("SELECT * FROM work_intervals WHERE user_id=? AND type IN (?,?,?,?) AND start_ts>=? "
                         "AND start_ts<?", (user_id, *BREAKS, _iso(d0), _iso(d0 + timedelta(days=1)))):
        end = _ist(iv["end_ts"]) if iv["end_ts"] else now.astimezone(IST)
        out[iv["type"]] += (end - _ist(iv["start_ts"])).total_seconds() / 60
    return {k: round(v, 1) for k, v in out.items()}


def end_session(user, body, now=None):
    """The forgotten timer: the person says when they stopped (on that day, not later than now)."""
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    iv = _open(me)
    if not iv:
        return state(user, now)
    end = _end_time(body)
    if not end:
        return base._bad("Give the time you stopped, like 2026-10-25T18:30.")
    start_at = _ist(iv["start_ts"])
    if not start_at < end <= now or end.date() != start_at.date():
        return base._bad("The stop time must be after the start, on the same day, and not in the future.")
    conn = store.connect()
    with conn:
        _close(conn, iv, end, me, "manual_end", "set by the person after a forgotten stop")
    return state(user, now)


def complete(user, task_id, body, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    t = _task(task_id)
    if not t or t["assigned_to"] != me:
        return 404, {"error": "not_found", "message": "No such task of yours."}
    if t["status"] not in WORKABLE:
        return 409, {"error": "not_workable", "message": f"This task is {t['status']}."}
    url = str((body or {}).get("evidence_url") or "").strip()
    if (url or not settings.TASKS_V3) and not base._valid_url(url):
        return base._bad("Add the proof link (http or https) before you complete it.")
    iv = _open(me)
    if _stale(iv, now):
        return 409, {"error": "open_session", "message": "Set when you stopped that earlier timer first."}
    conn = store.connect()
    with conn:
        if iv and iv["task_id"] == task_id:
            conn.execute("UPDATE work_intervals SET end_ts=? WHERE id=?", (_iso(now), iv["id"]))
        conn.execute("UPDATE work_tasks SET evidence_url=? WHERE id=?", (url, task_id))
        _set_status(conn, t, "submitted", me, "complete", now)
    return state(user, now)


# ------------------------------------------------------------------ v3: start / end my day
def _guard_v3(user, now=None):
    return _guard(user, write=True, now=now) or (None if settings.TASKS_V3 else ERR_OFF_V3)


def start_day(user, now=None):
    g = _guard_v3(user, now)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    today = work_date(now).isoformat()
    if not _day(me, today):
        status = "late" if now.astimezone(IST).strftime("%H:%M") > str(work_settings()["day_late_after"]) \
            else "on_time"
        conn = store.connect()
        try:
            with conn:
                conn.execute("INSERT INTO work_days(user_id, date, start_at, status) VALUES (?,?,?,?)",
                             (me, today, _iso(now), status))
                _event(conn, me, None, "day_start", now, "", status)
        except sqlite3.IntegrityError:
            pass  # a double click: the first press already started the day
    return state(user, now)


def end_day(user, now=None):
    g = _guard_v3(user, now)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    d = _day(me, work_date(now).isoformat())
    if not d:
        return 409, {"error": "day_not_started", "message": "Your day hasn't started."}
    if d["end_at"]:
        return state(user, now)
    iv = _open(me)
    if _stale(iv, now):
        return 409, {"error": "open_session", "message": "Set when you stopped that earlier timer first."}
    conn = store.connect()
    with conn:
        if iv:
            _close(conn, iv, now, me, "auto_pause", "day ended")
        conn.execute("UPDATE work_days SET end_at=?, end_source='button' WHERE id=?", (_iso(now), d["id"]))
        _event(conn, me, None, "day_end", now)
    return state(user, now)


def reopen_day(user, body, now=None):
    """Resume an ended day (today only): the person their own (flexible hours, work in parts), Jai anyone's.
    The old end stays in task_events."""
    g = _guard_v3(user, now)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    who = str((body or {}).get("user_id") or me)
    if who != me and not taskmgr.is_super(user):
        return ERR_SUPER
    d = _day(who, work_date(now).isoformat())
    if not d or not d["end_at"]:
        return 404, {"error": "not_found", "message": "That person has no ended day today."}
    conn = store.connect()
    with conn:
        conn.execute("UPDATE work_days SET end_at=NULL, end_source='reopened' WHERE id=?", (d["id"],))
        _event(conn, who, None, "day_reopen", now, "ended", "open",
               f"ended {_ist(d['end_at']):%H:%M}, reopened by " + ("the person" if who == me else "Jai"), actor=me)
    return state(user, now)


# ------------------------------------------------------------------ v3: working hours (Jai)
def _hours(v):
    try:
        h = float(v)
    except (TypeError, ValueError):
        return None
    return h if 0 <= h <= 16 else None


def set_week_hours(user, body, now=None):
    """New weekly hours from a date (default: the next work month, 26th). Never earlier than today,
    so past days keep their targets; everyone sees the change coming on their screen."""
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    now = _now(now)
    b = body or {}
    week = [_hours(v) for v in (b.get("week") or [])]
    if len(week) != 7 or None in week:
        return base._bad("Give 7 numbers, Monday to Sunday, each 0 to 16 hours.")
    today = work_date(now)
    try:
        start = _date.fromisoformat(b["from"]) if b.get("from") else cycle_bounds(cycle_of(today))[1] + timedelta(days=1)
    except ValueError:
        return base._bad("The start date looks like 2026-11-26.")
    if start < today:
        return base._bad("New hours can start today or later, never on past days.")
    store.write("INSERT INTO week_hours(week, effective_from, set_by, set_at) VALUES (?,?,?,?)",
                (json.dumps(week), start.isoformat(), base.uid(user), _iso(now)))
    return state(user, now)


def set_day_hours(user, body, now=None):
    """Hours for one date, for everyone. hours null = back to the weekly hours."""
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    b = body or {}
    try:
        day = _date.fromisoformat(str(b.get("date"))).isoformat()
    except ValueError:
        return base._bad("Pick a date.")
    if day < work_date(_now(now)).isoformat():
        return base._bad("Past days keep their hours.")
    hours = None if b.get("hours") is None else _hours(b.get("hours"))
    if b.get("hours") is not None and hours is None:
        return base._bad("Hours must be 0 to 16.")
    store.write("INSERT INTO day_hours(date, hours, note, set_by, set_at) VALUES (?,?,?,?,?)",
                (day, hours, str(b.get("note") or "")[:NOTE_MAX], base.uid(user), _iso(_now(now))))
    return state(user, now)


# ------------------------------------------------------------------ v3: hour credits
def allowance_hours(user_id):
    """Hours this person may be short in a month: their own row, else everyone's ('*'), else 0."""
    r = store.one("SELECT hours FROM hour_allowance WHERE user_id IN (?, '*') "
                  "ORDER BY user_id='*', id DESC LIMIT 1", (user_id,))
    return float(r["hours"]) if r else 0.0


def idle_minutes(user_id, d0, d1):
    """Idle after a dependency stop or a Waiting tap, d0 <= stop < d1 (IST dates): if nothing
    started within the grace, the whole gap until the next start (or the day's end) counts.
    Gaps are merged so a stop plus a Waiting tap never count twice."""
    a0, a1 = (_iso(_day_start(d)) for d in (d0, d1))
    stops = [r["t"] for r in store.rows(
        "SELECT start_ts t FROM task_holds WHERE user_id=? AND start_ts>=? AND start_ts<? UNION "
        "SELECT start_ts t FROM work_intervals WHERE user_id=? AND type='waiting' AND start_ts>=? AND start_ts<? "
        "ORDER BY t", (user_id, a0, a1, user_id, a0, a1))]
    grace = timedelta(seconds=work_settings()["idle_grace_seconds"])
    gaps = []
    for t in stops:
        s = _ist(t)
        nxt = store.one("SELECT MIN(start_ts) t FROM work_intervals WHERE user_id=? AND type IN (?,?) AND start_ts>=?",
                        (user_id, *COUNTS, t))["t"]
        d = _day(user_id, work_date(s).isoformat())
        end = min([_ist(x) for x in (nxt, d and d["end_at"]) if x] + [_day_start(work_date(s) + timedelta(days=1))])
        if end - s > grace:
            gaps.append([s, end])
    total, last = 0.0, None
    for s, e in gaps:
        s = max(s, last) if last else s
        if e > s:
            total += (e - s).total_seconds() / 60
        last = max(last, e) if last else e
    return round(total, 1)


def month_credit(user_id, month, now=None):
    """A work month (26th..25th) so far: finished days only, from the person's first day. Extra hours
    make up short days inside the same work month only; a closed month can't be topped up.
    Owed = short hours beyond the allowance, plus idle after dependency stops."""
    now = _now(now)
    first = store.one("SELECT MIN(date) d FROM work_days WHERE user_id=?", (user_id,))["d"]
    today = work_date(now)
    m0, m1 = cycle_bounds(month)
    d = max(m0, _date.fromisoformat(first)) if first else today
    start, worked, target, rings, ring_days = d, 0.0, 0.0, 0, 0
    while d < today and d <= m1:
        mins, goal = day_work(user_id, d.isoformat(), now)["provenMinutes"], user_target(user_id, d.isoformat()) * 60
        worked, target = worked + mins, target + goal
        if goal:
            ring_days, rings = ring_days + 1, rings + (mins >= goal)
        d += timedelta(days=1)
    idle = idle_minutes(user_id, start.isoformat(), d.isoformat()) if d > start else 0.0
    allow = allowance_hours(user_id) * 60
    from . import leave
    carried = leave.carried_hours(user_id, month) * 60 if settings.TASKS_V3 else 0.0
    balance = round(worked - target - idle + carried, 1)
    return {"month": month, "from": m0.isoformat(), "to": m1.isoformat(), "workedMinutes": round(worked, 1),
            "targetMinutes": target, "idleMinutes": idle, "balanceMinutes": balance, "allowanceMinutes": allow,
            "owedMinutes": max(0.0, -balance - allow), "ringsClosed": rings, "ringDays": ring_days,
            "carriedMinutes": carried}


def set_allowance(user, body, now=None):
    """Jai: hours someone (or everyone, user_id '*') may be short in a month."""
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    b = body or {}
    who = str(b.get("user_id") or "*")
    try:
        hours = float(b.get("hours"))
    except (TypeError, ValueError):
        hours = -1
    if not 0 <= hours <= 200 or (who != "*" and not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,))):
        return base._bad("Pick everyone or one person, and 0 to 200 hours.")
    store.write("INSERT INTO hour_allowance(user_id, hours, set_by, set_at) VALUES (?,?,?,?)",
                (who, hours, base.uid(user), _iso(_now(now))))
    return state(user, now)


# ------------------------------------------------------------------ v3: Jai's daily tasks
def _routines_public(rs):
    cats = {c["id"]: c["name"] for c in _categories(False)}
    return [{**r, "details": json.loads(r["details"] or "{}"), "category": cats.get(r["category_id"], "")}
            for r in rs]


def routines(user_id):
    """The daily tasks this person can jump to (theirs and everyone's)."""
    return _routines_public(store.rows("SELECT * FROM daily_routines WHERE active=1 AND user_id IN ('*', ?) "
                                       "ORDER BY id", (user_id,)))


def create_routine(user, body, now=None):
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    b = body or {}
    title = str(b.get("title") or "").strip()
    if not 3 <= len(title) <= 200:
        return base._bad("Give the daily task a title (3 to 200 characters).")
    cat, details = _details(b)
    if not cat:
        return details
    prio = b.get("priority") or "P2"
    who = str(b.get("user_id") or "*")
    if prio not in PRIO or (who != "*" and not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,))):
        return base._bad("Pick a priority and everyone or one person.")
    store.write("INSERT INTO daily_routines(title, category_id, details, priority, user_id, created_by, created_at) "
                "VALUES (?,?,?,?,?,?,?)", (title, cat["id"], json.dumps(details), prio, who, base.uid(user),
                                           _iso(_now(now))))
    return state(user, now)


def set_routine_active(user, routine_id, body, now=None):
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    if store.write("UPDATE daily_routines SET active=? WHERE id=?",
                   (int(bool((body or {}).get("active"))), routine_id)).rowcount != 1:
        return 404, {"error": "not_found", "message": "No such daily task."}
    return state(user, now)


def start_routine(user, routine_id, now=None):
    """Jump to a daily task: carry on today's copy if there is one, else make it, then start it."""
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    r = store.one("SELECT * FROM daily_routines WHERE id=? AND active=1 AND user_id IN ('*', ?)", (routine_id, me))
    if not r:
        return 404, {"error": "not_found", "message": "No such daily task."}
    t = store.one("SELECT id FROM work_tasks WHERE assigned_to=? AND status IN (?,?,?) "
                  "AND json_extract(details, '$.routine_id')=? ORDER BY id DESC", (me, *WORKABLE, routine_id))
    if not t:
        code, out = create_task(user, {"title": r["title"], "category_id": r["category_id"],
                                       "details": json.loads(r["details"]), "priority": r["priority"]},
                                 now, routine_id)
        if code != 201:
            return code, out
        t = out["task"]
    return start(user, t["id"], now)


# ------------------------------------------------------------------ road blockers
def block(user, task_id, body, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    b = body or {}
    t = _task(task_id)
    if not t or t["assigned_to"] != me:
        return 404, {"error": "not_found", "message": "No such task of yours."}
    if t["status"] not in WORKABLE:
        return 409, {"error": "not_workable", "message": f"This task is {t['status']}."}
    reason = str(b.get("reason") or "").strip()
    if settings.TASKS_V3:
        if reason not in work_settings()["block_reasons"]:
            return base._bad("Pick why you are stopped.")
        extra = str(b.get("detail") or "").strip()
        reason = f"{reason}: {extra}" if extra else reason
    who_id = str(b.get("depends_on_user_id") or "")
    who = store.one("SELECT name FROM dt_people WHERE user_id=?", (who_id,)) if who_id else None
    name = who["name"] if who else str(b.get("depends_on_name") or "").strip()
    if (who_id and not who) or not name or not reason:
        return base._bad("Say who you are waiting on and why.")
    iv = _open(me)
    if _stale(iv, now):
        return 409, {"error": "open_session", "message": "Set when you stopped that earlier timer first."}
    needs = (store.one("SELECT hold_needs_approval h FROM task_categories WHERE id=?",
                       (t["category_id"],)) or {}).get("h")
    conn = store.connect()
    with conn:
        if iv and iv["task_id"] == task_id:
            conn.execute("UPDATE work_intervals SET end_ts=? WHERE id=?", (_iso(now), iv["id"]))
        conn.execute("INSERT INTO task_holds(task_id, user_id, depends_on_user_id, depends_on_name, reason, "
                     "start_ts, status) VALUES (?,?,?,?,?,?,?)",
                     (task_id, me, who_id or None, name[:120], reason[:NOTE_MAX], _iso(now),
                      "pending" if needs else "noted"))
        _set_status(conn, t, "blocked", me, "block", now, f"waiting on {name}: {reason}")
    code, out = state(user, now)
    return code, {**out, "suggestions": suggestions(me, exclude=task_id), "needsApproval": bool(needs),
                  "routines": routines(me)}


def unblock(user, task_id, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    t = _task(task_id)
    if not t or t["assigned_to"] != me or t["status"] != "blocked":
        return 404, {"error": "not_found", "message": "No blocked task of yours with that number."}
    conn = store.connect()
    with conn:
        conn.execute("UPDATE task_holds SET end_ts=? WHERE task_id=? AND end_ts IS NULL", (_iso(now), task_id))
        _set_status(conn, t, "paused", me, "unblock", now)
    return state(user, now)


def decide_hold(user, hold_id, body, now=None):
    g = _guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    now = _now(now)
    h = store.one("SELECT * FROM task_holds WHERE id=?", (hold_id,))
    if not h or h["status"] != "pending":
        return 404, {"error": "not_found", "message": "No hold waiting for a decision."}
    ok = bool((body or {}).get("approve"))
    note = str((body or {}).get("note") or "")[:NOTE_MAX]
    conn = store.connect()
    with conn:
        conn.execute("UPDATE task_holds SET status=?, decided_by=?, decided_at=?, decision_note=? WHERE id=?",
                     ("approved" if ok else "rejected", base.uid(user), _iso(now), note, hold_id))
        _event(conn, h["user_id"], h["task_id"], "hold_approved" if ok else "hold_rejected", now,
               reason=note, actor=base.uid(user))
    return state(user, now)


# ------------------------------------------------------------------ 15-minute proof
def add_proof(user, body, now=None):
    g = _guard(user, now=now, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    b = body or {}
    slot = str(b.get("slot") or "")
    today = work_date(now).isoformat()
    if not slot.startswith(today):
        return 409, {"error": "locked", "message": "Only today's time can get proof. Earlier days are locked; "
                                                    "ask Jai for a correction."}
    worked = day_slots(me, today, now)
    if slot not in worked:
        return base._bad("There is no timer time in that 15 minutes.")
    url = str(b.get("url") or "").strip()
    image, logo = str(b.get("image_name") or "").strip(), str(b.get("logo_name") or "").strip()
    note = str(b.get("note") or "").strip()
    if url and not base._valid_url(url):
        return base._bad("The link must start with http:// or https://.")
    if not (url or image or logo) or not note:
        return base._bad("Add what you did and the proof: a link, an image name or a logo name.")
    p = urlparse(url) if url else None
    domain = str(b.get("domain") or ((p.hostname or "") if p else "")).strip().lower()
    slug = str(b.get("url_slug") or (p.path.strip("/") if p else "")).strip()
    try:
        store.write("INSERT INTO work_slots(user_id, task_id, slot_start, slot_minutes, url, domain, url_slug, "
                    "image_name, logo_name, note, server_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (me, worked[slot]["task_id"], slot, int(work_settings()["slot_minutes"]), url[:500],
                     domain[:200], slug[:300], image[:200], logo[:200], note[:NOTE_MAX], _iso(now)))
    except sqlite3.IntegrityError:
        return 409, {"error": "duplicate", "message": "Those 15 minutes already have proof."}
    return state(user, now)
