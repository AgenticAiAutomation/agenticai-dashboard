"""Follow-ups — the rules. Every function returns (http_status, payload).

Order of the "do now" list (the follow-up guide):
    1. overdue, oldest first
    2. today, by priority (P1 → P3), then time
Upcoming = the next 14 days by date; Done = the latest 20, newest first.
Each item carries the contact's phone / WhatsApp / email and the last thing
that happened with that contact, so the call starts from the log.
"""
import calendar as _cal
import re
from datetime import date as _date, datetime, timedelta

from . import store
from .config import settings

KINDS = {"call": "Call", "meeting": "Meet", "payment": "Collect payment from", "whatsapp": "WhatsApp",
         "email": "Email", "other": "Follow up with"}
PRIORITIES = ("P1", "P2", "P3")

ERR_AUTH = (401, {"error": "not_authenticated", "message": "Sign in to the dashboard first."})
ERR_FORBID = (403, {"error": "forbidden", "message": "Follow-ups are for the owner and the marketing team."})
ERR_FROZEN = (503, {"error": "read_only", "message": "Follow-ups are read-only for maintenance."})


def _bad(msg):
    return 400, {"error": "invalid", "message": msg}


def _email(user):
    return str((user or {}).get("email") or "").strip().lower()


def on_team(user):
    """On the owner's marketing list (fu_access)."""
    try:
        return bool(_email(user)) and bool(store.one(
            "SELECT 1 x FROM fu_access WHERE email=? AND removed_at IS NULL", (_email(user),)))
    except Exception:  # store not ready: only the superusers get in
        return False


def allowed(user):
    """Follow-ups and Leads: the superusers and the marketing team, whatever their dashboard role."""
    if not user:
        return False
    return (_email(user) in settings.SUPERUSERS or on_team(user)
            or str(user.get("role") or "").lower() in settings.ROLES)


def is_super(user):
    return bool(user) and str(user.get("email") or "").strip().lower() in settings.SUPERUSERS


def _guard(user, write=False):
    if not user:
        return ERR_AUTH
    if not allowed(user):
        return ERR_FORBID
    if write and settings.READ_ONLY:
        return ERR_FROZEN
    return None


def _dt(s):
    s = str(s or "").strip().replace(" ", "T")
    if len(s) == 10:
        s += "T10:00"
    return datetime.fromisoformat(s[:16])


def _fmt(d):
    return d.strftime("%Y-%m-%dT%H:%M")


def _digits(s):
    return re.sub(r"[^\d+]", "", str(s or ""))


# ------------------------------------------------------------------ contacts
CONTACT_FIELDS = ("name", "company", "phone", "whatsapp", "email", "city", "notes")


def _contact_clean(body, existing=None):
    c = dict(existing or {})
    for k in CONTACT_FIELDS:
        if k in (body or {}) and body[k] is not None:
            c[k] = str(body[k]).strip()[:2000 if k == "notes" else 160]
    if len(c.get("name", "")) < 2:
        return _bad("The contact needs a name."), None
    for k in ("phone", "whatsapp"):
        if c.get(k) and len(_digits(c[k]).lstrip("+")) < 8:
            return _bad(f"{k.title()} number looks too short."), None
    if c.get("email") and "@" not in c["email"]:
        return _bad("That email doesn't look right."), None
    return None, c


def last_log(contact_id):
    """The latest thing that happened with this contact: a done follow-up's
    outcome or a note, whichever is newer."""
    f = store.one("SELECT outcome text, done_at at, kind, title FROM crm_followups WHERE contact_id=? "
                  "AND status='done' AND outcome != '' ORDER BY done_at DESC LIMIT 1", (contact_id,))
    n = store.one("SELECT text, created_at at FROM crm_notes WHERE contact_id=? ORDER BY id DESC LIMIT 1",
                  (contact_id,))
    # Newest wins; on a tie the note (written after the call) wins.
    cands = [(x["at"] or "", i, x) for i, x in enumerate((f, n)) if x]
    best = max(cands)[2] if cands else None
    return {"text": best["text"], "at": (best["at"] or "")[:16]} if best else None


def _contact_public(c):
    out = dict(c)
    wa = _digits(c.get("whatsapp") or c.get("phone")).lstrip("+")
    if wa and len(wa) == 10:
        wa = "91" + wa                       # Indian mobile without country code
    out["waLink"] = f"https://wa.me/{wa}" if wa else ""
    out["telLink"] = f"tel:{_digits(c.get('phone'))}" if c.get("phone") else ""
    out["lastLog"] = last_log(c["id"])
    return out


def list_contacts(user, q=None):
    g = _guard(user)
    if g:
        return g
    sql, args = "SELECT * FROM crm_contacts", []
    if q:
        sql += " WHERE lower(name || ' ' || company || ' ' || phone || ' ' || email) LIKE ?"
        args.append(f"%{str(q).lower()}%")
    rows = store.rows(sql + " ORDER BY lower(name) LIMIT 500", args)
    return 200, {"contacts": [_contact_public(c) for c in rows]}


def get_contact(user, cid):
    g = _guard(user)
    if g:
        return g
    c = store.one("SELECT * FROM crm_contacts WHERE id=?", (cid,))
    if not c:
        return 404, {"error": "not_found", "message": "No such contact."}
    out = _contact_public(c)
    out["followups"] = [_fu_public(f, c) for f in store.rows(
        "SELECT * FROM crm_followups WHERE contact_id=? ORDER BY due_at DESC", (cid,))]
    out["notes"] = store.rows("SELECT * FROM crm_notes WHERE contact_id=? ORDER BY id DESC", (cid,))
    return 200, {"contact": out}


def create_contact(user, body):
    g = _guard(user, write=True)
    if g:
        return g
    err, c = _contact_clean(body)
    if err:
        return err
    lead_id = (body or {}).get("lead_id")
    if lead_id:
        have = store.one("SELECT id FROM crm_contacts WHERE lead_id=?", (int(lead_id),))
        if have:
            return get_contact(user, have["id"])
    now = store.now_iso()
    cur = store.write("INSERT INTO crm_contacts(name, company, phone, whatsapp, email, city, notes, lead_id, "
                      "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (c["name"], c.get("company", ""), c.get("phone", ""), c.get("whatsapp", ""),
                       c.get("email", ""), c.get("city", ""), c.get("notes", ""),
                       int(lead_id) if lead_id else None, user.get("name") or "", now, now))
    st, out = get_contact(user, cur.lastrowid)
    return 201, out


def update_contact(user, cid, body):
    g = _guard(user, write=True)
    if g:
        return g
    c = store.one("SELECT * FROM crm_contacts WHERE id=?", (cid,))
    if not c:
        return 404, {"error": "not_found", "message": "No such contact."}
    err, c2 = _contact_clean(body, c)
    if err:
        return err
    store.write("UPDATE crm_contacts SET name=?, company=?, phone=?, whatsapp=?, email=?, city=?, notes=?, "
                "updated_at=? WHERE id=?", tuple(c2.get(k, "") for k in CONTACT_FIELDS) + (store.now_iso(), cid))
    return get_contact(user, cid)


def add_note(user, cid, body):
    g = _guard(user, write=True)
    if g:
        return g
    if not store.one("SELECT id FROM crm_contacts WHERE id=?", (cid,)):
        return 404, {"error": "not_found", "message": "No such contact."}
    text = str((body or {}).get("text") or "").strip()
    if len(text) < 2:
        return _bad("Write what happened.")
    store.write("INSERT INTO crm_notes(contact_id, text, created_by, created_at) VALUES (?,?,?,?)",
                (cid, text[:4000], user.get("name") or "", store.stamp()))
    return get_contact(user, cid)


# ------------------------------------------------------------------ follow-ups
def guide(f, c):
    """One line a person can act on: 'Call Aman (Hospital Cloud.ai) — Follow-up call'."""
    who = c["name"] + (f" ({c['company']})" if c.get("company") else "")
    return f"{KINDS.get(f['kind'], 'Follow up with')} {who} — {f['title']}"


def _fu_public(f, c=None):
    c = c or store.one("SELECT * FROM crm_contacts WHERE id=?", (f["contact_id"],)) or {"name": "?", "id": 0}
    out = dict(f)
    now = store.now_ist()
    due = _dt(f["due_at"])
    out["guide"] = guide(f, c)
    out["overdue"] = f["status"] == "open" and (due.date() < now.date() if f["all_day"] else due < now)
    out["today"] = due.date() == now.date()
    out["contact"] = _contact_public(c) if c.get("id") else c
    return out


def _fu_clean(body, existing=None):
    f = dict(existing or {})
    b = body or {}
    for k in ("kind", "title", "priority", "location"):
        if k in b and b[k] is not None:
            f[k] = str(b[k]).strip()[:300]
    if "all_day" in b:
        f["all_day"] = 1 if b["all_day"] else 0
    if "due_at" in b and b["due_at"]:
        try:
            f["due_at"] = _fmt(_dt(b["due_at"]))
        except ValueError:
            return _bad("The date must look like 2026-10-26 or 2026-10-26T15:00."), None
    f.setdefault("kind", "call")
    f.setdefault("priority", "P2")
    f.setdefault("location", "")
    f.setdefault("all_day", 0)
    if f["kind"] not in KINDS:
        return _bad("Kind is call, meeting, payment, whatsapp, email or other."), None
    if f["priority"] not in PRIORITIES:
        return _bad("Priority is P1, P2 or P3."), None
    if len(f.get("title", "")) < 3:
        return _bad("Say what the follow-up is about."), None
    if not f.get("due_at"):
        return _bad("When? Pick a date (and time)."), None
    return None, f


def create_followup(user, body):
    g = _guard(user, write=True)
    if g:
        return g
    body = body or {}
    cid = body.get("contact_id")
    if not cid and isinstance(body.get("contact"), dict):
        st, out = create_contact(user, body["contact"])
        if st not in (200, 201):
            return st, out
        cid = out["contact"]["id"]
    c = store.one("SELECT * FROM crm_contacts WHERE id=?", (cid,)) if cid else None
    if not c:
        return _bad("Pick a contact or add a new one.")
    err, f = _fu_clean(body)
    if err:
        return err
    now = store.now_iso()
    cur = store.write("INSERT INTO crm_followups(contact_id, kind, title, due_at, all_day, priority, location, "
                      "prev_id, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (c["id"], f["kind"], f["title"], f["due_at"], f["all_day"], f["priority"], f["location"],
                       body.get("prev_id"), user.get("name") or "", now, now))
    return 201, {"followup": _fu_public(store.one("SELECT * FROM crm_followups WHERE id=?", (cur.lastrowid,)))}


def update_followup(user, fid, body):
    g = _guard(user, write=True)
    if g:
        return g
    f = store.one("SELECT * FROM crm_followups WHERE id=?", (fid,))
    if not f:
        return 404, {"error": "not_found", "message": "No such follow-up."}
    err, f2 = _fu_clean(body, f)
    if err:
        return err
    status = (body or {}).get("status")
    if status and status not in ("open", "cancelled"):
        return _bad("Use 'done' to finish a follow-up.")
    store.write("UPDATE crm_followups SET kind=?, title=?, due_at=?, all_day=?, priority=?, location=?, "
                "status=COALESCE(?, status), updated_at=? WHERE id=?",
                (f2["kind"], f2["title"], f2["due_at"], f2["all_day"], f2["priority"], f2["location"],
                 status, store.now_iso(), fid))
    return 200, {"followup": _fu_public(store.one("SELECT * FROM crm_followups WHERE id=?", (fid,)))}


def done(user, fid, body):
    """Close a follow-up with what happened; optionally book the next one."""
    g = _guard(user, write=True)
    if g:
        return g
    f = store.one("SELECT * FROM crm_followups WHERE id=?", (fid,))
    if not f:
        return 404, {"error": "not_found", "message": "No such follow-up."}
    if f["status"] != "open":
        return _bad("This follow-up is already closed.")
    body = body or {}
    outcome = str(body.get("outcome") or "").strip()
    if len(outcome) < 3:
        return _bad("Write what happened — the next call starts from this.")
    nxt = body.get("next")
    if nxt:
        err, _ = _fu_clean(dict(nxt, title=nxt.get("title") or f["title"]))
        if err:
            return err
    store.write("UPDATE crm_followups SET status='done', outcome=?, done_at=?, done_by=?, updated_at=? WHERE id=?",
                (outcome[:4000], store.stamp(), user.get("name") or "", store.now_iso(), fid))
    _billing_paid(f)
    out = {"followup": _fu_public(store.one("SELECT * FROM crm_followups WHERE id=?", (fid,)))}
    if nxt:
        st, n = create_followup(user, dict(nxt, contact_id=f["contact_id"], prev_id=fid,
                                           title=nxt.get("title") or f["title"]))
        out["next"] = n.get("followup")
    return 200, out


def snooze(user, fid, body):
    g = _guard(user, write=True)
    if g:
        return g
    f = store.one("SELECT * FROM crm_followups WHERE id=?", (fid,))
    if not f or f["status"] != "open":
        return 404, {"error": "not_found", "message": "No open follow-up with that id."}
    to = (body or {}).get("due_at")
    if not to:
        to = _fmt(_dt(f["due_at"]) + timedelta(days=1))
    return update_followup(user, fid, {"due_at": to})


def board(user, days=14):
    """To do (overdue + today, priority order), upcoming, done."""
    g = _guard(user)
    if g:
        return g
    sync_billing()
    now = store.now_ist()
    today = now.date().isoformat()
    end = (now.date() + timedelta(days=int(days or 14))).isoformat()
    contacts = {c["id"]: c for c in store.rows("SELECT * FROM crm_contacts")}
    hide = "" if is_super(user) else " AND (ref IS NULL OR ref NOT LIKE 'billing:%')"
    open_ = [_fu_public(f, contacts.get(f["contact_id"])) for f in
             store.rows("SELECT * FROM crm_followups WHERE status='open'" + hide + " ORDER BY due_at")]
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    overdue = [f for f in open_ if f["overdue"]]
    todays = sorted((f for f in open_ if not f["overdue"] and f["due_at"][:10] == today),
                    key=lambda f: (pri[f["priority"]], f["due_at"]))
    upcoming = [f for f in open_ if not f["overdue"] and today < f["due_at"][:10] <= end]
    later = sum(1 for f in open_ if f["due_at"][:10] > end)
    done_ = [_fu_public(f, contacts.get(f["contact_id"])) for f in
             store.rows("SELECT * FROM crm_followups WHERE status='done'" + hide + " ORDER BY done_at DESC LIMIT 20")]
    return 200, {"now": _fmt(now), "todo": overdue + todays, "overdue": len(overdue), "today": len(todays),
                 "upcoming": upcoming, "later": later, "done": done_, "kinds": KINDS}


def calendar(user, start=None, end=None):
    g = _guard(user)
    if g:
        return g
    now = store.now_ist().date()
    start = str(start or now.replace(day=1).isoformat())[:10]
    end = str(end or (now + timedelta(days=45)).isoformat())[:10]
    sync_billing()
    contacts = {c["id"]: c for c in store.rows("SELECT * FROM crm_contacts")}
    hide = "" if is_super(user) else " AND (ref IS NULL OR ref NOT LIKE 'billing:%')"
    items = [_fu_public(f, contacts.get(f["contact_id"])) for f in store.rows(
        "SELECT * FROM crm_followups WHERE status != 'cancelled' AND substr(due_at,1,10) BETWEEN ? AND ?" + hide +
        " ORDER BY due_at", (start, end))]
    return 200, {"from": start, "to": end, "items": items}


def status(user):
    if not user:
        return ERR_AUTH
    return 200, {"enabled": True, "allowed": allowed(user), "superuser": is_super(user),
                 "version": settings.VERSION}


# ------------------------------------------------------------------ marketing team (owner only)
def team(user):
    if not is_super(user):
        return 403, {"error": "forbidden", "message": "Only the owner manages the marketing team."}
    return 200, {"team": store.rows("SELECT email, name, added_at FROM fu_access WHERE removed_at IS NULL "
                                    "ORDER BY name, email")}


def team_add(user, body):
    if not is_super(user):
        return 403, {"error": "forbidden", "message": "Only the owner manages the marketing team."}
    email = str((body or {}).get("email") or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return _bad("Give their dashboard login email.")
    if email in settings.SUPERUSERS:
        return _bad("The owner always has access.")
    if not store.one("SELECT 1 x FROM fu_access WHERE email=? AND removed_at IS NULL", (email,)):
        store.write("INSERT INTO fu_access(email, name, added_by, added_at) VALUES (?,?,?,?)",
                    (email, str((body or {}).get("name") or "").strip()[:120], _email(user), store.now_iso()))
    return team(user)


def team_remove(user, body):
    if not is_super(user):
        return 403, {"error": "forbidden", "message": "Only the owner manages the marketing team."}
    email = str((body or {}).get("email") or "").strip().lower()
    store.write("UPDATE fu_access SET removed_by=?, removed_at=? WHERE email=? AND removed_at IS NULL",
                (_email(user), store.now_iso(), email))
    return team(user)


# ------------------------------------------------------------------ projects + billing (Jai only)
CYCLES = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12}
CYCLE_LABEL = {"monthly": "monthly", "quarterly": "quarterly", "half_yearly": "half-yearly", "yearly": "yearly"}


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, _cal.monthrange(y, m)[1]))


def _ref(p):
    return f"billing:{p['id']}:{p['next_due']}"


def sync_billing():
    """Every active recurring project with a next due date has exactly one open
    payment follow-up, due REMIND_DAYS before. Anything else that was made for
    it (old date, project now one-time or inactive) is cancelled, never deleted."""
    want = {}
    for p in store.rows("SELECT * FROM crm_projects"):
        if p["active"] and p["billing"] == "recurring" and p["next_due"] and p["contact_id"]:
            want[_ref(p)] = p
    for f in store.rows("SELECT id, ref FROM crm_followups WHERE status='open' AND ref LIKE 'billing:%'"):
        if f["ref"] not in want:
            store.write("UPDATE crm_followups SET status='cancelled', updated_at=? WHERE id=?",
                        (store.now_iso(), f["id"]))
    for ref, p in want.items():
        have = store.one("SELECT id, status FROM crm_followups WHERE ref=?", (ref,))
        if have:
            if have["status"] == "cancelled":       # switched back to recurring: reopen it
                store.write("UPDATE crm_followups SET status='open', updated_at=? WHERE id=?",
                            (store.now_iso(), have["id"]))
            continue
        due = _date.fromisoformat(p["next_due"]) - timedelta(days=settings.REMIND_DAYS)
        title = (f"Payment due {_date.fromisoformat(p['next_due']).strftime('%d %b %Y')} for {p['name']} "
                 f"({CYCLE_LABEL[p['cycle']]} plan)" + (f" · {p['amount_note']}" if p["amount_note"] else ""))
        now = store.now_iso()
        try:
            store.write("INSERT INTO crm_followups(contact_id, kind, title, due_at, priority, ref, created_by, "
                        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (p["contact_id"], "payment", title[:300], f"{due.isoformat()}T10:00", "P1", ref,
                         "billing", now, now))
        except Exception:
            pass                               # another worker made it first (unique ref)


def _billing_paid(f):
    """A payment reminder marked done = paid: the next due date moves on one cycle."""
    ref = f.get("ref") or ""
    if not ref.startswith("billing:"):
        return
    _, pid, due = ref.split(":", 2)
    p = store.one("SELECT * FROM crm_projects WHERE id=?", (int(pid),))
    if not p or p["billing"] != "recurring" or p["next_due"] != due:
        return
    nxt = _add_months(_date.fromisoformat(due), CYCLES[p["cycle"]]).isoformat()
    store.write("UPDATE crm_projects SET next_due=?, updated_at=? WHERE id=?", (nxt, store.now_iso(), p["id"]))
    sync_billing()


def _project_public(p):
    out = dict(p)
    c = store.one("SELECT * FROM crm_contacts WHERE id=?", (p["contact_id"],)) if p["contact_id"] else None
    out["contact"] = _contact_public(c) if c else None
    rem = store.one("SELECT id, due_at, status FROM crm_followups WHERE ref=?", (_ref(p),)) if p["next_due"] else None
    out["reminder"] = rem
    if p["billing"] == "recurring" and p["next_due"]:
        out["daysToDue"] = (_date.fromisoformat(p["next_due"]) - store.now_ist().date()).days
    return out


def _sites():
    try:
        from app.backlink_ops import seed
        from app.backlink_ops import store as bo_store
        return {k: v.get("domain") or v.get("name") for k, v in seed.projects(bo_store.get_config()).items()}
    except Exception:
        return {}


def _project_clean(body, existing=None):
    p = dict(existing or {})
    b = body or {}
    for k in ("name", "site_id", "amount_note", "notes"):
        if k in b and b[k] is not None:
            p[k] = str(b[k]).strip()[:300 if k != "notes" else 2000]
    if "billing" in b:
        p["billing"] = str(b["billing"])
    if "cycle" in b and b["cycle"]:
        p["cycle"] = str(b["cycle"])
    if "next_due" in b:
        p["next_due"] = str(b["next_due"] or "")[:10] or None
    if "active" in b:
        p["active"] = 1 if b["active"] else 0
    p.setdefault("billing", "one_time")
    p.setdefault("cycle", "monthly")
    if len(p.get("name", "")) < 2:
        return _bad("The project needs a name."), None
    if p["billing"] not in ("one_time", "recurring"):
        return _bad("Billing is one_time or recurring."), None
    if p["cycle"] not in CYCLES:
        return _bad("Cycle is monthly, quarterly, half_yearly or yearly."), None
    if p.get("next_due"):
        try:
            _date.fromisoformat(p["next_due"])
        except ValueError:
            return _bad("Next payment date must look like 2026-11-30."), None
    if p["billing"] == "recurring" and not p.get("next_due"):
        return _bad("A recurring project needs its next payment date."), None
    return None, p


def _super_guard(user, write=False):
    g = _guard(user, write)
    if g:
        return g
    if not is_super(user):
        return 403, {"error": "forbidden", "message": "Projects and billing are for Jai only."}
    return None


def list_projects(user):
    g = _super_guard(user)
    if g:
        return g
    sync_billing()
    return 200, {"projects": [_project_public(p) for p in store.rows(
        "SELECT * FROM crm_projects ORDER BY active DESC, lower(name)")],
                 "sites": _sites(), "cycles": list(CYCLES), "remindDays": settings.REMIND_DAYS}


def create_project(user, body):
    g = _super_guard(user, write=True)
    if g:
        return g
    body = body or {}
    err, p = _project_clean(body)
    if err:
        return err
    cid = body.get("contact_id")
    if not cid:
        cust = body.get("contact") if isinstance(body.get("contact"), dict) else {"name": p["name"] + " (customer)"}
        st, out = create_contact(user, cust)
        if st not in (200, 201):
            return st, out
        cid = out["contact"]["id"]
    elif not store.one("SELECT id FROM crm_contacts WHERE id=?", (cid,)):
        return _bad("Unknown customer contact.")
    now = store.now_iso()
    cur = store.write("INSERT INTO crm_projects(name, site_id, contact_id, billing, cycle, next_due, amount_note, notes, "
                      "active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                      (p["name"], p.get("site_id", ""), int(cid), p["billing"], p["cycle"], p.get("next_due"),
                       p.get("amount_note", ""), p.get("notes", ""), now, now))
    sync_billing()
    return 201, {"project": _project_public(store.one("SELECT * FROM crm_projects WHERE id=?", (cur.lastrowid,)))}


def update_project(user, pid, body):
    """Any time: one-time ↔ recurring, cycle, next date, customer, active."""
    g = _super_guard(user, write=True)
    if g:
        return g
    p = store.one("SELECT * FROM crm_projects WHERE id=?", (pid,))
    if not p:
        return 404, {"error": "not_found", "message": "No such project."}
    err, p2 = _project_clean(body, p)
    if err:
        return err
    cid = (body or {}).get("contact_id") or p["contact_id"]
    store.write("UPDATE crm_projects SET name=?, site_id=?, contact_id=?, billing=?, cycle=?, next_due=?, amount_note=?, "
                "notes=?, active=?, updated_at=? WHERE id=?",
                (p2["name"], p2.get("site_id", ""), cid, p2["billing"], p2["cycle"], p2.get("next_due"),
                 p2.get("amount_note", ""), p2.get("notes", ""), p2.get("active", 1), store.now_iso(), pid))
    sync_billing()
    return 200, {"project": _project_public(store.one("SELECT * FROM crm_projects WHERE id=?", (pid,)))}
