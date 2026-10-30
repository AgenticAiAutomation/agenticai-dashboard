"""Tasks v3 Big Ideas (Jai, 30 Oct): how to make Agentic AI Automation the most watched company
on the internet: social media, ChatGPT, Gemini, DeepSeek, Grok, Perplexity, Claude, Copilot, Maps.

  * the board is open to everyone, so people check nobody gave the idea already
  * everyone owes ideas_required (1) a month; ideas_for_nomination (6) counted in a month = nominee
  * Jai marks each idea: assigned (to whom, on which project: a task lands on their desk),
    worked, not_applied, or repeat (given before by anyone, Jai included: not counted)
  * Employee of the Month: Jai picks from the nominees by what was proven and applied; final
  * Wins (Step 7): achievements for the company or a client; Jai approves, rejects (final) or asks
    for more. Bonus sheet per work month: eligible = this month's idea given AND at least one
    worked idea or approved Win. Hours and leave are shown, never part of eligibility (Jai, 30 Oct)
"""
import csv
import io
from datetime import datetime, timezone

from . import service as base, store, taskmgr, worktime as wt

STATUSES = ("new", "assigned", "worked", "not_applied", "repeat")
DECISIONS = ("approved", "rejected", "more")
NOTE_MAX = 2000


def _month(now):
    """The work month (26th..25th): an idea after the 25th counts for the next one."""
    return wt.cycle_of(wt.work_date(now))


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
    wins = store.rows("SELECT * FROM achievements ORDER BY id DESC LIMIT 500")
    for w in wins:
        w["name"] = names.get(w["user_id"], w["user_id"])
    return 200, {"month": month, "ideas": ideas, "people": people, "channels": cfg["idea_channels"],
                 "required": cfg["ideas_required"], "forNomination": cfg["ideas_for_nomination"],
                 "me": base.uid(user), "isSuperuser": taskmgr.is_super(user), "statuses": STATUSES,
                 "projects": list(base.sites(user)[0]) if taskmgr.is_super(user) else [],
                 "employeeOfMonth": eom and {**eom, "name": names.get(eom["user_id"], eom["user_id"])},
                 "wins": wins if taskmgr.is_super(user) else [w for w in wins if w["user_id"] == base.uid(user)],
                 "bonus": bonus_sheet(month, now) if taskmgr.is_super(user) else None}


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


# ------------------------------------------------------------------ Wins (Step 7)
def _win_fields(b):
    f = {k: str(b.get(k) or "").strip() for k in ("what", "for_whom", "result", "proof_url")}
    if not 10 <= len(f["what"]) <= NOTE_MAX or not 2 <= len(f["for_whom"]) <= 200 or not 3 <= len(f["result"]) <= NOTE_MAX:
        return None, base._bad("Say what you did, for whom (the company or a client) and the result.")
    if f["proof_url"] and not base._valid_url(f["proof_url"]):
        return None, base._bad("The proof link must start with http:// or https://.")
    return f, None


def submit_win(user, body, now=None):
    g = wt._guard_v3(user)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    f, err = _win_fields(body or {})
    if err:
        return err
    store.write("INSERT INTO achievements(user_id, month, what, for_whom, result, proof_url, created_at) "
                "VALUES (?,?,?,?,?,?,?)", (base.uid(user), _month(now), f["what"], f["for_whom"], f["result"],
                                           f["proof_url"][:500], wt._iso(now)))
    return board(user, now)


def edit_win(user, win_id, body, now=None):
    """After Jai asks for more, the person fixes it and it goes back to Jai."""
    g = wt._guard_v3(user)
    if g:
        return g
    w = store.one("SELECT * FROM achievements WHERE id=? AND user_id=?", (win_id, base.uid(user)))
    if not w or w["status"] != "more":
        return 404, {"error": "not_found", "message": "No Win of yours waiting for more detail."}
    f, err = _win_fields(body or {})
    if err:
        return err
    store.write("UPDATE achievements SET what=?, for_whom=?, result=?, proof_url=?, status='pending' WHERE id=?",
                (f["what"], f["for_whom"], f["result"], f["proof_url"][:500], win_id))
    return board(user, now)


def decide_win(user, win_id, body, now=None):
    g = wt._guard(user, write=True, superuser=True) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    b = body or {}
    w = store.one("SELECT * FROM achievements WHERE id=?", (win_id,))
    if not w or w["status"] not in ("pending", "more"):
        return 404, {"error": "not_found", "message": "No Win waiting for a decision."}
    st = b.get("decision")
    note = str(b.get("note") or "").strip()[:NOTE_MAX]
    if st not in DECISIONS:
        return base._bad("Approve, reject or ask for more.")
    if st == "more" and not note:
        return base._bad("Say what more you need.")
    conn = store.connect()
    with conn:
        conn.execute("UPDATE achievements SET status=?, note=?, decided_by=?, decided_at=? WHERE id=?",
                     (st, note, base.uid(user), wt._iso(now), win_id))
        wt._event(conn, w["user_id"], None, "win_" + st, now, w["status"], st, f"win #{win_id}", actor=base.uid(user))
    return board(user, now)


def bonus_sheet(month, now=None):
    """One row per person for a work month. Jai decides amounts outside the system."""
    cfg = wt.work_settings()
    rows = []
    for p in store.rows("SELECT user_id, name FROM dt_people ORDER BY name"):
        ideas = store.rows("SELECT status FROM big_ideas WHERE user_id=? AND month=? AND status!='repeat'",
                           (p["user_id"], month))
        worked = sum(i["status"] == "worked" for i in ideas)
        wins = store.one("SELECT COUNT(*) c FROM achievements WHERE user_id=? AND month=? AND status='approved'",
                         (p["user_id"], month))["c"]
        c = wt.month_credit(p["user_id"], month, now)
        rows.append({"user_id": p["user_id"], "name": p["name"], "ideas": len(ideas),
                     "ideaGiven": len(ideas) >= cfg["ideas_required"], "ideasWorked": worked, "winsApproved": wins,
                     "ringsClosed": c["ringsClosed"], "ringDays": c["ringDays"], "owedMinutes": c["owedMinutes"],
                     "nominated": len(ideas) >= cfg["ideas_for_nomination"],
                     "eligible": len(ideas) >= cfg["ideas_required"] and (worked + wins) > 0})
    return rows


def bonus_csv(user, month=None, now=None):
    g = wt._guard(user, superuser=True) or (None if wt.settings.TASKS_V3 else wt.ERR_OFF_V3)
    if g:
        return g
    now = now or datetime.now(timezone.utc)
    month = month or _month(now)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Work month", "Name", "Ideas counted", "Monthly idea given", "Ideas worked", "Wins approved",
                "Rings closed", "Days with a target", "Hours owed", "Nominated", "Bonus eligible"])
    for r in bonus_sheet(month, now):
        w.writerow([month, r["name"], r["ideas"], "yes" if r["ideaGiven"] else "no", r["ideasWorked"],
                    r["winsApproved"], r["ringsClosed"], r["ringDays"], round(r["owedMinutes"] / 60, 2),
                    "yes" if r["nominated"] else "no", "yes" if r["eligible"] else "no"])
    return 200, out.getvalue()
