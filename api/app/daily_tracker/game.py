"""Tasks v3 Step 6: points, streaks, levels, badges, weekly leaderboard.

  * task points = estimate hours x points_per_hour (20: 15m = 5, 30m = 10, 1h = 20, 3h = 60)
    x complexity (Easy 1, Medium 1.5, Hard 2); pending until Jai accepts the Done task
  * a worked Big Idea and an approved Win earn points too (idea_worked_points, win_points)
  * streak = working days in a row with the day's target met; days with no target
    (Sunday, a 0-hour date) don't break it. shortcut: approved leave doesn't exist yet (Step 9)
  * badges are worked out from what happened and written once (badges_awarded is append-only)
  * leaderboard: this week's points and target days met, never hours
"""
import json
from datetime import datetime, timedelta, timezone

from . import service as base, store, taskmgr, worktime as wt

COMPLEXITY = ("Easy", "Medium", "Hard")
SCAN_DAYS = 60   # streaks and day badges look this far back


def task_points(t, cfg=None):
    cfg = cfg or wt.work_settings()
    details = t["details"] if isinstance(t["details"], dict) else json.loads(t["details"] or "{}")
    mult = cfg["complexity_multiplier"].get(details.get("complexity"), 1)
    return round((t["estimate_min"] or 0) / 60 * cfg["points_per_hour"] * mult)


def _award(conn, user_id, rule, ref, points, reason, by="system", task_id=None, now=None):
    conn.execute("INSERT OR IGNORE INTO work_points(user_id, task_id, rule, ref, points, reason, awarded_by, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?)", (user_id, task_id, rule, ref, points, reason, by, wt._iso(now or wt._now())))


def _badge(conn, user_id, code, ref, now):
    conn.execute("INSERT OR IGNORE INTO badges_awarded(user_id, code, ref, awarded_by, awarded_at) VALUES (?,?,?,?,?)",
                 (user_id, code, ref, "system", wt._iso(now)))


def review(user, task_id, body, now=None):
    """Jai accepts a Done task (its points are earned) or sends it back (it waits as paused)."""
    g = wt._guard(user, now=now, write=True, superuser=True) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = wt._now(now)
    t = wt._task(task_id)
    if not t or t["status"] != "submitted":
        return 404, {"error": "not_found", "message": "No Done task waiting for you with that number."}
    ok = bool((body or {}).get("accept"))
    note = str((body or {}).get("note") or "").strip()[:wt.NOTE_MAX]
    if not ok and not note:
        return wt.base._bad("Say what needs fixing.")
    conn = store.connect()
    with conn:
        wt._set_status(conn, t, "accepted" if ok else "paused", t["assigned_to"], "accept" if ok else "send_back",
                       now, note, actor=base.uid(user))
        if ok:
            pts = task_points(t)
            _award(conn, t["assigned_to"], "task", f"task:{task_id}", pts, t["title"][:200], base.uid(user), task_id, now)
    return wt.state(user, now)


def _days(user_id, now):
    """[(date, target met?)] for days with a target, oldest first, finished days + today if already met."""
    today = wt.work_date(now)
    first = store.one("SELECT MIN(date) d FROM work_days WHERE user_id=?", (user_id,))["d"]
    if not first:
        return []
    d = max(today - timedelta(days=SCAN_DAYS), datetime.fromisoformat(first).date())
    out = []
    while d <= today:
        goal = wt.target_hours(d.isoformat()) * 60
        if goal:
            met = wt.day_work(user_id, d.isoformat(), now)["provenMinutes"] >= goal
            if d < today or met:
                out.append((d, met))
        d += timedelta(days=1)
    return out


def refresh(user_id, now=None):
    """Award what was earned and not written yet. Idempotent; returns the current streak."""
    now = wt._now(now)
    cfg = wt.work_settings()
    days = _days(user_id, now)
    streak = 0
    conn = store.connect()
    with conn:
        for d, met in days:
            streak = streak + 1 if met else 0
            if met:
                _badge(conn, user_id, "ring_closer", d.isoformat(), now)
            for n in (5, 20):
                if streak == n:
                    _badge(conn, user_id, f"streak_{n}d", d.isoformat(), now)
        for r in store.rows("SELECT date FROM work_days WHERE user_id=? AND status='on_time'", (user_id,)):
            _badge(conn, user_id, "early_bird", r["date"], now)
        hard = {}
        for e in store.rows("SELECT e.server_ts, t.details FROM task_events e JOIN work_tasks t ON t.id=e.task_id "
                            "WHERE e.user_id=? AND e.event_type='accept'", (user_id,)):
            if json.loads(e["details"] or "{}").get("complexity") == "Hard":
                y, w, _ = wt._ist(e["server_ts"]).isocalendar()
                hard[f"{y}-W{w:02d}"] = hard.get(f"{y}-W{w:02d}", 0) + 1
        for week, n in hard.items():
            if n >= 5:
                _badge(conn, user_id, "hard_mode", week, now)
        for h in store.rows("SELECT id, start_ts FROM task_holds WHERE user_id=?", (user_id,)):
            nxt = store.one("SELECT MIN(start_ts) t FROM work_intervals WHERE user_id=? AND type IN (?,?) AND start_ts>=?",
                            (user_id, *wt.COUNTS, h["start_ts"]))["t"]
            if nxt and (wt._ist(nxt) - wt._ist(h["start_ts"])).total_seconds() <= 120:
                _badge(conn, user_id, "blocker_buster", f"hold:{h['id']}", now)
        for r in store.rows("SELECT month FROM big_ideas WHERE user_id=? AND status!='repeat' GROUP BY month "
                            "HAVING COUNT(*)>=?", (user_id, cfg["ideas_required"])):
            _badge(conn, user_id, "idea_maker", r["month"], now)
        for i in store.rows("SELECT id, title FROM big_ideas WHERE user_id=? AND status='worked'", (user_id,)):
            _award(conn, user_id, "idea_worked", f"idea:{i['id']}", cfg["idea_worked_points"], i["title"][:200], now=now)
        for w in store.rows("SELECT id, what FROM achievements WHERE user_id=? AND status='approved'", (user_id,)):
            _badge(conn, user_id, "achiever", f"win:{w['id']}", now)
            _award(conn, user_id, "win", f"win:{w['id']}", cfg["win_points"], w["what"][:200], now=now)
    return streak


def _week_start(now):
    d = wt.work_date(now)
    return d - timedelta(days=d.weekday())


def summary(user_id, now=None):
    now = wt._now(now)
    cfg = wt.work_settings()
    streak = refresh(user_id, now)
    total = store.one("SELECT COALESCE(SUM(points),0) p FROM work_points WHERE user_id=?", (user_id,))["p"]
    pending = sum(task_points(t, cfg) for t in store.rows(
        "SELECT * FROM work_tasks WHERE assigned_to=? AND status='submitted'", (user_id,)))
    levels = sorted(cfg["levels"], key=lambda x: x[1])
    level = [l for l in levels if total >= l[1]][-1] if levels else ["", 0]
    nxt = next((l for l in levels if l[1] > total), None)
    names = {b["code"]: b["name"] for b in store.rows("SELECT code, name FROM badges")}
    badges = [{"code": r["code"], "name": names.get(r["code"], r["code"]), "count": r["n"]} for r in store.rows(
        "SELECT code, COUNT(*) n FROM badges_awarded WHERE user_id=? GROUP BY code ORDER BY MIN(awarded_at)", (user_id,))]
    return {"points": total, "pending": pending, "streak": streak, "level": level[0],
            "nextLevel": nxt and {"name": nxt[0], "at": nxt[1]}, "badges": badges}


def leaderboard(now=None):
    """This week (Monday on): points earned and target days met. Never hours."""
    now = wt._now(now)
    start = _week_start(now)
    since = wt._iso(wt._day_start(start))
    out = []
    for p in store.rows("SELECT user_id, name FROM dt_people ORDER BY name"):
        pts = store.one("SELECT COALESCE(SUM(points),0) p FROM work_points WHERE user_id=? AND created_at>=?",
                        (p["user_id"], since))["p"]
        rings, d = 0, start
        while d <= wt.work_date(now):  # counted here, not from badges: those are written when the person looks
            goal = wt.target_hours(d.isoformat()) * 60
            rings += bool(goal) and wt.day_work(p["user_id"], d.isoformat(), now)["provenMinutes"] >= goal
            d += timedelta(days=1)
        if pts or rings or store.one("SELECT 1 x FROM work_days WHERE user_id=? AND date>=?", (p["user_id"], start.isoformat())):
            out.append({"user_id": p["user_id"], "name": p["name"], "points": pts, "rings": rings})
    return sorted(out, key=lambda r: (-r["points"], -r["rings"], r["name"]))


def to_review():
    """Jai's queue: Done tasks waiting to be accepted, with the points they'd earn."""
    cfg = wt.work_settings()
    names = {p["user_id"]: p["name"] for p in store.rows("SELECT user_id, name FROM dt_people")}
    return [{"id": t["id"], "title": t["title"], "name": names.get(t["assigned_to"], t["assigned_to"]),
             "estimate_min": t["estimate_min"], "complexity": json.loads(t["details"] or "{}").get("complexity", ""),
             "points": task_points(t, cfg), "done_at": t["updated_at"]}
            for t in store.rows("SELECT * FROM work_tasks WHERE status='submitted' ORDER BY updated_at")]
