"""Backlink Ops — one level per (person, website). v1.3, FEATURE_PER_PROJECT_LEVELS.

Before v1.3 there was one level for the whole desk, and the Today score added
up every link on a site, whoever logged it: two associates on DIYMart shared
one bar, and moving Akash up moved everyone up.

Now:
  * bo_user_levels holds the level for each (dashboard user id, site).
  * A pair seen for the first time starts at the desk's global level, so the
    upgrade drops nobody back to level 1.
  * The person's own day is their links only, at their own level. Each link is
    still scored against the whole site's sheet for that day, so the numbers
    match the All-projects tab.
  * XP, streak and last completed day are recomputed from the links on read
    (the links stay the source of truth; the row is the level plus a cache).
  * The level itself only changes when the superuser changes it — the
    existing rule ("raise after five clean days in a row") is kept, and a
    pair that has earned it shows as ready.
"""
from datetime import date as _date, timedelta

from . import store
from .assignments import norm
from .scoring import day_stats
from .seed import LEVELS, level as level_for

READY_STREAK = 5


def user_key(user):
    return str(user.get("id") or user.get("email") or user.get("name") or "")


def ensure(user, project, cfg):
    uid = user_key(user)
    row = store.get_level(uid, project)
    if row is None:
        L = level_for(int((cfg or {}).get("level", 1) or 1), cfg)
        return store.create_level(uid, project, user.get("name", ""), user.get("email", ""),
                                  L["n"], L["name"])
    if row["user_name"] != (user.get("name") or "") or row["user_email"] != (user.get("email") or ""):
        row = store.update_level(uid, project, user_name=user.get("name") or "",
                                 user_email=user.get("email") or "")
    return row


def my_day(user, project, date, cfg, row=None):
    """This person's own day on this site, at their own level."""
    row = row or ensure(user, project, cfg)
    who = norm(user.get("name"))
    site = store.entries_for(project, date)
    mine = [e for e in site if norm(e["author"]) == who]
    queries = [q for q in store.queries_for(project, date) if norm(q["author"]) == who]
    st = day_stats(mine, store.decisions_for(project, date), queries, row["level"], project,
                   store.bank_keywords(project), cfg, group=site)
    st.pop("rows", None)
    st["pair"] = public(row, cfg)
    return st


def refresh(row, cfg):
    """Recompute XP, streak and last completed day for one pair from its links.
    Returns the public view, including today's progress."""
    project, name = row["project_id"], row["user_name"]
    entries = store.entries_by_author(project, name)
    qdates = store.query_dates_by_author(project, name)
    dates = sorted({e["date"] for e in entries} | set(qdates))
    today = store.today_ist()
    by_date = {}
    for e in entries:
        by_date.setdefault(e["date"], []).append(e)

    xp, done_days, today_st = 0.0, set(), None
    if dates:
        groups = store.entries_on(project, dates)
        decisions = store.decisions_by_ids(e["id"] for g in groups.values() for e in g)
        bank = store.bank_keywords(project)
        for d in dates:
            mine = by_date.get(d, [])
            st = day_stats(mine, decisions, [None] * qdates.get(d, 0), row["level"], project,
                           bank, cfg, group=groups.get(d) or mine)
            xp += st["points"]
            if st["done"] and (mine or qdates.get(d)):
                done_days.add(d)
            if d == today:
                today_st = st

    streak = 0
    day = _date.fromisoformat(today)
    if today not in done_days:          # today still in progress: it cannot break the streak
        day -= timedelta(days=1)
    while day.isoformat() in done_days:
        streak += 1
        day -= timedelta(days=1)

    L = level_for(row["level"], cfg)
    row = store.update_level(row["user_id"], project, xp=round(xp, 1), streak_days=streak,
                             last_completed_date=max(done_days) if done_days else None,
                             current_difficulty=L["name"])
    out = public(row, cfg)
    out.update({"todayPoints": today_st["points"] if today_st else 0,
                "todayDone": bool(today_st and today_st["done"]),
                "todayLinks": today_st["counted"] if today_st else 0})
    return out


def set_level(user_id, project, level, cfg):
    L = level_for(level, cfg)
    return store.update_level(str(user_id), project, level=L["n"], current_difficulty=L["name"])


def public(row, cfg):
    L = level_for(row["level"], cfg)
    return {"userId": row["user_id"], "name": row["user_name"], "email": row["user_email"],
            "project": row["project_id"], "level": L["n"], "levelName": L["name"],
            "difficulty": row["current_difficulty"] or L["name"], "xp": row["xp"],
            "streak": row["streak_days"], "lastCompleted": row["last_completed_date"],
            "target": L["target"], "minLinks": L.get("min_links", 0), "queries": L["queries"],
            "ready": row["streak_days"] >= READY_STREAK and L["n"] < len(LEVELS),
            "seededFrom": row.get("seeded_from")}


def level_lookup(cfg):
    """{(normalised name, project): level n} for the board and All-projects tab,
    which only know authors by name."""
    return {(norm(r["user_name"]), r["project_id"]): r["level"] for r in store.all_levels()}
