"""Tasks v3 leave (Jai, 30 Oct): per work month (26th..25th) everyone gets leave_days_per_month full
days and short_leaves_per_month short leaves of up to short_leave_hours each; Jai can set any person
differently (leave_policy, latest row wins, a person's own row beats '*').

  * a full day excuses that day's hours; a short leave excuses its hours (that day's target drops)
  * unused leave carries forward as hours to the next work month only: days x daily_target_hours
    + short leaves x short_leave_hours, added to that month's credit
  * leave is today or later, inside the allowance; it can be cancelled (once) until its day passes.
    Rows live in leave_calendar (v2 table): type full | short, credited_hours = hours excused
"""
from datetime import date as _date, timedelta

from . import service as base, store, taskmgr, worktime as wt

TYPES = ("full", "short")


def policy(user_id):
    """{days, short_count, short_hours} for this person."""
    r = store.one("SELECT days, short_count, short_hours FROM leave_policy WHERE user_id IN (?, '*') "
                  "ORDER BY user_id='*', id DESC LIMIT 1", (user_id,))
    if r:
        return dict(r)
    cfg = wt.work_settings()
    return {"days": cfg["leave_days_per_month"], "short_count": cfg["short_leaves_per_month"],
            "short_hours": cfg["short_leave_hours"]}


def leaves(user_id, d0, d1):
    """Active leave rows d0..d1 (inclusive)."""
    return store.rows("SELECT * FROM leave_calendar WHERE user_id=? AND cancelled_at IS NULL AND type IN ('full','short') "
                      "AND date>=? AND date<=? ORDER BY date", (user_id, str(d0), str(d1)))


def excused_hours(user_id, day):
    r = store.one("SELECT COALESCE(SUM(credited_hours),0) h FROM leave_calendar WHERE user_id=? AND date=? "
                  "AND cancelled_at IS NULL", (user_id, str(day)))
    return float(r["h"])


def used(user_id, cycle):
    m0, m1 = wt.cycle_bounds(cycle)
    rs = leaves(user_id, m0, m1)
    return {"days": sum(r["type"] == "full" for r in rs), "short": sum(r["type"] == "short" for r in rs), "rows": rs}


def carried_hours(user_id, cycle):
    """Unused leave of the work month before, as hours (only if the person had started by then)."""
    m0, _ = wt.cycle_bounds(cycle)
    prev = wt.cycle_of(m0 - timedelta(days=1))
    first = store.one("SELECT MIN(date) d FROM work_days WHERE user_id=?", (user_id,))["d"]
    if not first or first > wt.cycle_bounds(prev)[1].isoformat():
        return 0.0
    p, u = policy(user_id), used(user_id, prev)
    return round(max(0, p["days"] - u["days"]) * wt.work_settings()["daily_target_hours"]
                 + max(0, p["short_count"] - u["short"]) * p["short_hours"], 2)


def summary(user_id, cycle):
    p, u = policy(user_id), used(user_id, cycle)
    return {"policy": p, "usedDays": u["days"], "usedShort": u["short"], "leaves": u["rows"],
            "carriedHours": carried_hours(user_id, cycle)}


def take(user, body, now=None):
    g = wt._guard_v3(user, now)
    if g:
        return g
    now = wt._now(now)
    me = base.uid(user)
    b = body or {}
    kind = b.get("type")
    try:
        day = _date.fromisoformat(str(b.get("date")))
    except ValueError:
        return base._bad("Pick the date.")
    if kind not in TYPES:
        return base._bad("Full day or short leave.")
    if day < wt.work_date(now):
        return base._bad("Leave is for today or later.")
    target = wt.target_hours(day.isoformat())
    if not target:
        return base._bad("No working hours that day, so no leave is needed.")
    p, u = policy(me), used(me, wt.cycle_of(day))
    if kind == "full":
        if u["days"] >= p["days"]:
            return base._bad(f"You've used your {p['days']} leave days this work month.")
        hours = target
    else:
        if u["short"] >= p["short_count"]:
            return base._bad(f"You've used your {p['short_count']} short leaves this work month.")
        try:
            hours = float(b.get("hours"))
        except (TypeError, ValueError):
            hours = 0
        if not 0 < hours <= min(p["short_hours"], target):
            return base._bad(f"A short leave is up to {p['short_hours']} hours.")
    if store.one("SELECT 1 x FROM leave_calendar WHERE user_id=? AND date=? AND cancelled_at IS NULL", (me, day.isoformat())):
        return 409, {"error": "duplicate", "message": "You already have leave that day."}
    store.write("INSERT INTO leave_calendar(user_id, date, type, credited_hours, reason, declared_by, declared_at) "
                "VALUES (?,?,?,?,?,?,?)", (me, day.isoformat(), kind, hours, str(b.get("reason") or "")[:300], me, wt._iso(now)))
    return wt.state(user, now)


def cancel(user, leave_id, now=None):
    """Your own leave until its day passes; Jai anyone's."""
    g = wt._guard_v3(user, now)
    if g:
        return g
    now = wt._now(now)
    r = store.one("SELECT * FROM leave_calendar WHERE id=? AND cancelled_at IS NULL", (leave_id,))
    mine = r and r["user_id"] == base.uid(user)
    if not r or not (mine or taskmgr.is_super(user)):
        return 404, {"error": "not_found", "message": "No such leave."}
    if mine and not taskmgr.is_super(user) and r["date"] < wt.work_date(now).isoformat():
        return base._bad("That day has passed; ask Jai.")
    store.write("UPDATE leave_calendar SET cancelled_by=?, cancelled_at=? WHERE id=?", (base.uid(user), wt._iso(now), leave_id))
    return wt.state(user, now)


def set_policy(user, body, now=None):
    """Jai: leave for everyone ('*') or one person."""
    g = wt._guard(user, now=now, write=True, superuser=True)
    if g:
        return g
    b = body or {}
    who = str(b.get("user_id") or "*")
    try:
        days, count, hours = int(b.get("days")), int(b.get("short_count")), float(b.get("short_hours"))
    except (TypeError, ValueError):
        return base._bad("Give leave days, short leaves and their hours.")
    if not (0 <= days <= 31 and 0 <= count <= 31 and 0 <= hours <= 8) or \
            (who != "*" and not store.one("SELECT 1 x FROM dt_people WHERE user_id=?", (who,))):
        return base._bad("Days and short leaves 0 to 31, short leave 0 to 8 hours, for everyone or one person.")
    store.write("INSERT INTO leave_policy(user_id, days, short_count, short_hours, set_by, set_at) VALUES (?,?,?,?,?,?)",
                (who, days, count, hours, base.uid(user), wt._iso(wt._now(now))))
    return wt.state(user, now)
