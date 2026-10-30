"""Tasks v3 Big Ideas (Jai, 30 Oct): how to make Agentic AI Automation the most watched company
on the internet: social media, ChatGPT, Gemini, DeepSeek, Grok, Perplexity, Claude, Copilot, Maps.

  * the board is open to everyone, so people check nobody gave the idea already
  * everyone owes ideas_required (1) a month; ideas_for_nomination (6) counted in a month = nominee
  * Jai marks each idea: assigned (to whom, on which project: a task lands on their desk),
    worked, not_applied, or repeat (given before by anyone, Jai included: not counted)
  * Employee of the Month: Jai picks from the nominees by what was proven and applied; final
"""
from datetime import datetime, timezone

from . import service as base, store, taskmgr, worktime as wt

STATUSES = ("new", "assigned", "worked", "not_applied", "repeat")
NOTE_MAX = 2000


def _month(now):
    return now.astimezone(store.IST).strftime("%Y-%m")


def board(user, now=None):
    g = wt._guard(user) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    month = _month(now)
    cfg = wt.work_settings()
    names = {p["user_id"]: p["name"] for p in store.rows("SELECT user_id, name FROM dt_people")}
    ideas = store.rows("SELECT * FROM big_ideas ORDER BY id DESC LIMIT 500")
    for i in ideas:
        i["name"] = names.get(i["user_id"], i["user_id"])
        i["assignedName"] = names.get(i["assigned_to"] or "", "")
    people = []
    for uid, name in sorted(names.items(), key=lambda x: x[1]):
        mine = [i for i in ideas if i["user_id"] == uid and i["month"] == month and i["status"] != "repeat"]
        people.append({"user_id": uid, "name": name, "counted": len(mine),
                       "worked": sum(i["status"] == "worked" for i in mine),
                       "assigned": sum(i["status"] == "assigned" for i in mine),
                       "nominated": len(mine) >= cfg["ideas_for_nomination"]})
    eom = store.one("SELECT * FROM employee_of_month WHERE month=?", (month,))
    return 200, {"month": month, "ideas": ideas, "people": people, "channels": cfg["idea_channels"],
                 "required": cfg["ideas_required"], "forNomination": cfg["ideas_for_nomination"],
                 "me": base.uid(user), "isSuperuser": taskmgr.is_super(user), "statuses": STATUSES,
                 "projects": list(base.sites(user)[0]) if taskmgr.is_super(user) else [],
                 "employeeOfMonth": eom and {**eom, "name": names.get(eom["user_id"], eom["user_id"])}}


def submit(user, body, now=None):
    g = wt._guard_v3(user)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    b = body or {}
    title, idea, channel = (str(b.get(k) or "").strip() for k in ("title", "idea", "channel"))
    if not 4 <= len(title) <= 140:
        return base._bad("Give the idea a short title (4 to 140 characters).")
    if not 20 <= len(idea) <= NOTE_MAX:
        return base._bad("Describe how it works in a few sentences (20 to 2000 characters).")
    if channel not in wt.work_settings()["idea_channels"]:
        return base._bad("Pick where it makes us show up.")
    store.write("INSERT INTO big_ideas(user_id, month, title, channel, idea, created_at) VALUES (?,?,?,?,?,?)",
                (base.uid(user), _month(now), title, channel, idea, wt._iso(now)))
    return board(user, now)


def decide(user, idea_id, body, now=None):
    """Jai sets the status. 'assigned' needs a person and a project, and puts a task on their desk."""
    g = wt._guard(user, write=True, superuser=True) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    b = body or {}
    i = store.one("SELECT * FROM big_ideas WHERE id=?", (idea_id,))
    if not i:
        return 404, {"error": "not_found", "message": "No such idea."}
    st = b.get("status")
    if st not in STATUSES:
        return base._bad("Unknown status.")
    who, project, task_id = i["assigned_to"], i["project"], i["task_id"]
    if st == "assigned":
        who, project = str(b.get("assign_to") or ""), str(b.get("project") or "").strip()
        if not who or not project:
            return base._bad("Say who applies it and on which project.")
        if who != i["assigned_to"] or not task_id:
            other = store.one("SELECT id FROM task_categories WHERE name LIKE 'Other%'")
            code, out = wt.create_task(user, {"title": f"Apply idea: {i['title']}"[:200], "assign_to": who,
                                              "category_id": other and other["id"], "domain": project,
                                              "details": {"description": i["idea"][:300]}}, now)
            if code != 201:
                return code, out
            task_id = out["task"]["id"]
    note = str(b.get("note") if b.get("note") is not None else i["note"])[:NOTE_MAX]
    conn = store.connect()
    with conn:
        conn.execute("UPDATE big_ideas SET status=?, assigned_to=?, project=?, task_id=?, note=?, decided_by=?, "
                     "decided_at=? WHERE id=?", (st, who, project, task_id, note, base.uid(user), wt._iso(now), idea_id))
        wt._event(conn, i["user_id"], task_id, "idea_" + st, now, i["status"], st, f"big idea #{idea_id}",
                  actor=base.uid(user))
    return board(user, now)


def pick_employee_of_month(user, body, now=None):
    """Jai's pick from this month's nominees. Final: one row per month, never changed."""
    g = wt._guard(user, write=True, superuser=True) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    code, b = board(user, now)
    who = str((body or {}).get("user_id") or "")
    p = next((p for p in b["people"] if p["user_id"] == who and p["nominated"]), None)
    if not p:
        return base._bad("Pick one of this month's nominees.")
    if b["employeeOfMonth"]:
        return 409, {"error": "chosen", "message": "This month's Employee of the Month is already chosen."}
    store.write("INSERT INTO employee_of_month(month, user_id, score, note, chosen_by, chosen_at) VALUES (?,?,?,?,?,?)",
                (b["month"], who, p["worked"], str((body or {}).get("note") or "")[:300], base.uid(user), wt._iso(now)))
    return board(user, now)
