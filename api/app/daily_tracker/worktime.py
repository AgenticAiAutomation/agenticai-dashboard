"""Tasks v2 — the task timer, the 15-minute proof and road blockers (Step 2).

The server is the truth. Every action closes or opens a work_intervals row and
writes a task_events row in one transaction; the browser only displays.

  * one running task per person: starting another pauses the first
  * an interval left open on an earlier day blocks everything until the person
    sets its end time (never invented by the server)
  * worked time = work intervals, merged (never double-counted), cut into
    15-minute slots; a slot counts only once it has proof
  * yesterday is locked: proof only for today's slots
  * road blocker: the watch stops at once, a task_holds row waits for Jai when
    the category says so, and the person gets their next task suggested

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
ERR_SUPER = (403, {"error": "forbidden", "message": "Only Jai can decide that."})
WORKABLE = ("todo", "paused", "in_progress")
DONE = ("submitted", "accepted", "cancelled")
PRIO = {"P1": 1, "P2": 2, "P3": 3}
COUNTS = ("work", "thinking")          # interval types that are effective work
NOTE_MAX = 300


class _Taken(Exception):
    """Someone else picked the pool task a moment earlier."""


# ------------------------------------------------------------------ helpers
def _guard(user, write=False, superuser=False):
    if not settings.TASKS_V2:
        return ERR_OFF
    if not user:
        return base.ERR_AUTH
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


def _slot_key(dt):
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M")


def work_settings():
    r = store.one("SELECT value FROM work_settings ORDER BY id DESC LIMIT 1")
    out = dict(store.DEFAULT_WORK_SETTINGS)
    out.update(json.loads(r["value"]) if r else {})
    return out


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
    return bool(iv) and _ist(iv["start_ts"]).date() < now.astimezone(IST).date()


def _close(conn, iv, now, user_id, kind="pause", reason=""):
    """Close the open interval and pause its task (if it was the running one)."""
    conn.execute("UPDATE work_intervals SET end_ts=? WHERE id=?", (_iso(now), iv["id"]))
    t = _task(iv["task_id"]) if iv["task_id"] else None
    if t and t["status"] == "in_progress":
        _set_status(conn, t, "paused", user_id, kind, now, reason)


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


# ------------------------------------------------------------------ time math
def _spans(user_id, day, now):
    """[(start, end, task_id)] of effective work on that IST day, clipped to the day."""
    d0 = datetime.fromisoformat(day).replace(tzinfo=IST)
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
    proven = {r["slot_start"] for r in store.rows(
        "SELECT slot_start FROM work_slots WHERE user_id=? AND slot_start LIKE ?", (user_id, day + "%"))}
    return {"workedMinutes": round(sum(s["minutes"] for s in slots.values()), 1),
            "provenMinutes": round(sum(s["minutes"] for k, s in slots.items() if k in proven), 1),
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
    g = _guard(user)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    today = now.astimezone(IST).date().isoformat()
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
    target = float(cfg["daily_target_hours"]) * 60
    return 200, {
        "now": _iso(now), "today": today,
        "running": iv and {"interval": iv, "task": iv["task_id"] and _public(_task(iv["task_id"]), cats),
                           "stale": _stale(iv, now)},
        "tasks": [_public(t, cats) for t in mine], "pool": [_public(t, cats) for t in pool],
        "holds": holds, "approve": approve,
        "categories": [c for c in cats.values() if c["active"]],
        "people": store.rows("SELECT user_id, name FROM dt_people ORDER BY name"),
        "work": {**work, "targetMinutes": target, "leftMinutes": max(0.0, target - work["provenMinutes"])},
        "settings": {"slotMinutes": cfg["slot_minutes"], "dailyTargetHours": cfg["daily_target_hours"]},
        "isSuperuser": taskmgr.is_super(user),
    }


# ------------------------------------------------------------------ tasks
def create_task(user, body, now=None):
    g = _guard(user, write=True)
    if g:
        return g
    now = _now(now)
    b = body or {}
    me = base.uid(user)
    title = str(b.get("title") or "").strip()
    if not 3 <= len(title) <= 200:
        return base._bad("Give the task a title (3 to 200 characters).")
    cat = next((c for c in _categories() if c["id"] == b.get("category_id")), None)
    if not cat:
        return base._bad("Pick a category.")
    given = b.get("details") or {}
    details = {}
    for f in cat["fields"]:
        v = str(given.get(f["key"]) or "").strip()
        if not v or (f["type"] == "choice" and v not in f["options"]):
            return base._bad(f"{cat['name']}: fill in “{f['label']}”.")
        details[f["key"]] = v[:NOTE_MAX]
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
    g = _guard(user, write=True)
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
    g = _guard(user, write=True)
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


def end_session(user, body, now=None):
    """The forgotten timer: the person says when they stopped (on that day, not later than now)."""
    g = _guard(user, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    iv = _open(me)
    if not iv:
        return state(user, now)
    try:
        end = datetime.fromisoformat(str((body or {}).get("end"))).replace(tzinfo=IST)
    except ValueError:
        return base._bad("Give the time you stopped, like 2026-10-25T18:30.")
    start_at = _ist(iv["start_ts"])
    if not start_at < end <= now or end.date() != start_at.date():
        return base._bad("The stop time must be after the start, on the same day, and not in the future.")
    conn = store.connect()
    with conn:
        _close(conn, iv, end, me, "manual_end", "set by the person after a forgotten stop")
    return state(user, now)


def complete(user, task_id, body, now=None):
    g = _guard(user, write=True)
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
    if not base._valid_url(url):
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


# ------------------------------------------------------------------ road blockers
def block(user, task_id, body, now=None):
    g = _guard(user, write=True)
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
    return code, {**out, "suggestions": suggestions(me, exclude=task_id), "needsApproval": bool(needs)}


def unblock(user, task_id, now=None):
    g = _guard(user, write=True)
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
    g = _guard(user, write=True, superuser=True)
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
    g = _guard(user, write=True)
    if g:
        return g
    now = _now(now)
    me = base.uid(user)
    b = body or {}
    slot = str(b.get("slot") or "")
    today = now.astimezone(IST).date().isoformat()
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
