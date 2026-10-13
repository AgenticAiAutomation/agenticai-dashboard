"""Daily Tracker + Idea Board — the rules, with no web framework in sight.

Every function takes the resolved user dict ({id, name, email, role}) or None
plus plain arguments and returns (http_status, payload). routes.py is a thin
translator.

Marks (spec §4B):
    marks = base marks of the work type (copied onto the log when submitted)
          × quality multiplier (1 → 0×, 2 → 0.5×, 3 → 1×, 4 → 1.25×, 5 → 1.5×)
          × 0.5 if the log was submitted after the day the work was done
Only APPROVED logs count. Pending ones show as "pending review".

Backlink Ops (spec: "no double entry, no double marks"): links logged on that
desk are shown here automatically, read-only, as "Backlink built". Each
approved one earns that type's marks, capped per day (settings), and the same
URL cannot be logged here by hand.

Who sees what: a person works on the sites they are rostered on in Backlink
Ops (the same check T1 fixed). Reviewers (owner/admin role or a superuser
email) see every site and every person.
"""
import csv
import io
import re
from calendar import monthrange
from datetime import date as _date, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from . import store
from .config import settings

QUALITY = {1: 0.0, 2: 0.5, 3: 1.0, 4: 1.25, 5: 1.5}
LOG_STATUSES = ("submitted", "approved", "needs_fix", "rejected")
IDEA_STATUSES = ("new", "shortlisted", "in_trial", "worked", "didnt_work")
BACKDATE_DAYS = 7
NOTE_MAX = 300

ERR_AUTH = (401, {"error": "not_authenticated", "message": "Sign in to the dashboard first."})
ERR_ADMIN = (403, {"error": "forbidden", "message": "Only Jai or an admin can do that."})
ERR_FROZEN = (503, {"error": "read_only",
                    "message": "The tracker is read-only while maintenance runs. Try again shortly."})
ERR_TRACKER_OFF = (404, {"error": "disabled", "message": "The Daily Tracker is not switched on."})
ERR_IDEAS_OFF = (404, {"error": "disabled", "message": "The Idea Board is not switched on."})


def _bad(msg, code="invalid", status=400):
    return status, {"error": code, "message": msg}


# ------------------------------------------------------------------ who
def uid(user):
    return str(user.get("id") or user.get("email") or "")


def is_admin(user):
    if not user:
        return False
    email = str(user.get("email") or "").strip().lower()
    return email in settings.SUPERUSERS or str(user.get("role") or "").lower() in settings.ADMIN_ROLES


def _seen(user):
    store.write("INSERT INTO dt_people(user_id, name, email, role, last_seen) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, email=excluded.email, "
                "role=excluded.role, last_seen=excluded.last_seen",
                (uid(user), user.get("name") or "", (user.get("email") or "").lower(),
                 user.get("role") or "", store.now_iso()))


def _guard(user, kind, write=False, admin=False):
    if kind == "tracker" and not settings.TRACKER:
        return ERR_TRACKER_OFF
    if kind == "ideas" and not settings.IDEAS:
        return ERR_IDEAS_OFF
    if not user:
        return ERR_AUTH
    if admin and not is_admin(user):
        return ERR_ADMIN
    if write and settings.READ_ONLY:
        return ERR_FROZEN
    return None


# ------------------------------------------------------------------ sites (Backlink Ops)
def _bo():
    """Backlink Ops modules, or None when that desk is off/missing."""
    try:
        from app.backlink_ops.config import settings as bo_settings
        if not bo_settings.ENABLED:
            return None
        from app.backlink_ops import assignments, seed
        from app.backlink_ops import store as bo_store
        return bo_store, seed, assignments
    except Exception:
        return None


def sites(user):
    """({id: site}, [ids this user may log on])."""
    bo = _bo()
    if bo:
        bo_store, seed, assignments = bo
        try:
            cfg = bo_store.get_config()
            known = seed.projects(cfg)
            allowed = list(known) if is_admin(user) else assignments.assigned_projects(user, cfg)
        except Exception:
            known, allowed = {}, []
    else:
        try:
            from app.backlink_ops.seed import projects
            known = projects()
        except Exception:
            known = {}
        allowed = [k for k, v in known.items() if v.get("active") is not False]
    slim = {k: {"id": k, "name": v.get("name"), "short": v.get("short") or k,
                "domain": v.get("domain", ""), "hue": v.get("hue", "#5B6B68"),
                "active": v.get("active") is not False} for k, v in known.items()}
    return slim, allowed


def _norm_name(s):
    return " ".join(str(s or "").split()).lower()


def backlink_rows(names, d_from, d_to):
    """Backlink Ops links by these people (names, case-insensitive) in a date
    range, with their review status. Read-only; [] if that desk is off."""
    bo = _bo()
    if not bo or not names:
        return []
    bo_store = bo[0]
    want = {_norm_name(n) for n in names if n}
    try:
        got = bo_store.connect().execute(
            "SELECT e.id, e.project, e.date, e.author, e.url, e.type, e.da, "
            "COALESCE(r.status, 'pending') status FROM bo_entries e "
            "LEFT JOIN bo_reviews r ON r.entry_id = e.id WHERE e.date BETWEEN ? AND ? "
            "ORDER BY e.date, e.created_at", (d_from, d_to)).fetchall()
    except Exception:
        return []
    return [dict(r) for r in got if _norm_name(r["author"]) in want]


def _bo_url_exists(key):
    bo = _bo()
    if not bo:
        return False
    try:
        host = key.split("/")[0].split("?")[0]
        for r in bo[0].connect().execute("SELECT url FROM bo_entries WHERE lower(url) LIKE ?",
                                         ("%" + host + "%",)):
            if proof_key(r["url"]) == key:
                return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------------ helpers
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)")


def proof_key(url):
    """The same link written two ways compares equal: scheme, www., case of
    the host, trailing slash, #fragment and tracking parameters ignored."""
    try:
        u = urlparse(str(url).strip())
    except Exception:
        return str(url).strip().lower()
    host = (u.hostname or "").lower().removeprefix("www.")
    path = u.path.rstrip("/") or ""
    q = urlencode(sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                         if not _TRACKING.match(k.lower())))
    return urlunparse(("", host, path, "", q, ""))[2:] if host else str(url).strip().lower()


def _valid_url(url):
    try:
        u = urlparse(url)
        return u.scheme in ("http", "https") and "." in (u.hostname or "")
    except Exception:
        return False


def marks_for(base, quality, late, cfg):
    m = float(base) * QUALITY.get(int(quality or 0), 0.0)
    if late:
        m *= float(cfg.get("late_factor", 0.5))
    return round(m, 2)


def _types():
    return {t["id"]: t for t in store.rows("SELECT * FROM work_types")}


def _backlink_type():
    return store.one("SELECT * FROM work_types WHERE kind='backlink' ORDER BY id LIMIT 1")


def _public_log(r, types, known):
    t = types.get(r["work_type_id"]) or {}
    return {"id": r["id"], "userId": r["user_id"], "userName": r["user_name"],
            "userEmail": r["user_email"], "project": r["project_id"],
            "site": (known.get(r["project_id"]) or {}).get("short", r["project_id"]),
            "workTypeId": r["work_type_id"], "workType": t.get("name", "?"),
            "baseMarks": r["base_marks"], "proofUrl": r["proof_url"], "note": r["note"],
            "minutes": r["minutes"], "date": r["log_date"], "submittedAt": r["submitted_at"],
            "late": bool(r["late"]), "status": r["status"], "quality": r["quality"],
            "marks": r["marks_awarded"], "reviewer": r["reviewer_name"],
            "reviewedAt": r["reviewed_at"], "reviewNote": r["review_note"], "source": "manual"}


def _days(d_from, d_to):
    a, b = _date.fromisoformat(d_from), _date.fromisoformat(d_to)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _range(kind, today):
    t = _date.fromisoformat(today)
    if kind == "week":
        return (t - timedelta(days=6)).isoformat(), today
    if kind == "month":
        return t.replace(day=1).isoformat(), today
    return today, today


# ------------------------------------------------------------------ status + types
def status(user):
    if not (settings.TRACKER or settings.IDEAS):
        return ERR_TRACKER_OFF
    if not user:
        return ERR_AUTH
    _seen(user)
    known, allowed = sites(user)
    cfg = store.get_settings()
    today = store.today_ist()
    badges = store.rows("SELECT month, kind, idea_id FROM user_badges WHERE user_id=? "
                        "ORDER BY month DESC", (uid(user),))
    return 200, {"tracker": settings.TRACKER, "ideas": settings.IDEAS,
                 "version": settings.VERSION, "readOnly": settings.READ_ONLY,
                 "me": {"id": uid(user), "name": user.get("name"), "email": user.get("email")},
                 "isAdmin": is_admin(user), "sites": known, "allowed": allowed,
                 "today": today, "backdateDays": BACKDATE_DAYS, "noteMax": NOTE_MAX,
                 "target": store.target_for(uid(user), today, cfg["default_daily_target"]),
                 "settings": cfg if is_admin(user) else None, "badges": badges}


def work_types(user):
    g = _guard(user, "tracker")
    if g:
        return g
    sql = "SELECT * FROM work_types" + ("" if is_admin(user) else " WHERE active=1") + \
          " ORDER BY sort_order, id"
    return 200, {"types": store.rows(sql)}


def put_work_types(user, body):
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    items = (body or {}).get("types")
    if not isinstance(items, list) or not items:
        return _bad("Send the list of work types.")
    for t in items:
        name = str(t.get("name") or "").strip()[:80]
        if not name:
            return _bad("Every work type needs a name.")
        try:
            marks = max(0.0, min(500.0, float(t.get("base_marks", 0))))
            order = int(t.get("sort_order") or 0)
        except (TypeError, ValueError):
            return _bad(f"{name}: marks and order must be numbers.")
        active = 1 if t.get("active", True) else 0
        if t.get("id"):
            store.write("UPDATE work_types SET name=?, base_marks=?, active=?, sort_order=? WHERE id=?",
                        (name, marks, active, order, int(t["id"])))
        else:
            if store.one("SELECT id FROM work_types WHERE lower(name)=lower(?)", (name,)):
                return _bad(f"'{name}' already exists.")
            store.write("INSERT INTO work_types(name, base_marks, active, sort_order, kind) "
                        "VALUES (?,?,?,?, '')", (name, marks, active, order or 999))
    return work_types(user)


# ------------------------------------------------------------------ logs
def _check_log(user, body, cfg, exclude_id=None):
    """Validates a submission. Returns (error, clean_fields)."""
    known, allowed = sites(user)
    project = str(body.get("project_id") or body.get("project") or "").strip()
    if project not in allowed:
        return _bad("Pick one of your sites. If yours is missing, ask Jai to put you on it "
                    "in Backlink Ops → Difficulty & team."), None
    try:
        wt = store.one("SELECT * FROM work_types WHERE id=? AND active=1",
                       (int(body.get("work_type_id") or 0),))
    except (TypeError, ValueError):
        wt = None
    if not wt:
        return _bad("Pick a work type from the list."), None
    url = str(body.get("proof_url") or "").strip()
    if not url:
        return _bad("A proof link is required — paste the URL of the work."), None
    if not _valid_url(url):
        return _bad("The proof link must be a full web address starting with http:// or https://."), None
    note = str(body.get("note") or "").strip()
    if len(note) > NOTE_MAX:
        return _bad(f"Keep the note under {NOTE_MAX} characters."), None
    if wt["kind"] == "other" and len(note) < 5:
        return _bad("For “Other”, describe what you did in the note."), None
    try:
        minutes = int(body.get("minutes") or 0)
    except (TypeError, ValueError):
        return _bad("Time spent must be a whole number of minutes."), None
    if not 0 <= minutes <= 1440:
        return _bad("Time spent must be between 0 and 1440 minutes."), None
    today = store.today_ist()
    log_date = str(body.get("date") or today)[:10]
    try:
        d = _date.fromisoformat(log_date)
    except ValueError:
        return _bad("The date must look like 2026-10-13."), None
    if d > _date.fromisoformat(today):
        return _bad("You can't log work for a future day."), None
    if (_date.fromisoformat(today) - d).days > BACKDATE_DAYS:
        return _bad(f"Logs older than {BACKDATE_DAYS} days need Jai — ask him to add it."), None

    key = proof_key(url)
    dup = store.one("SELECT id, user_name, log_date FROM daily_logs WHERE proof_key=? "
                    "AND status != 'rejected'" + (" AND id != ?" if exclude_id else ""),
                    (key, exclude_id) if exclude_id else (key,))
    if dup:
        return _bad(f"This link is already logged (by {dup['user_name']} on {dup['log_date']}). "
                    "The same link can't earn marks twice.", "duplicate", 409), None
    if _bo_url_exists(key):
        return _bad("This link is already in Backlink Ops, so it shows here automatically — "
                    "no need to log it again.", "duplicate", 409), None
    return None, {"project_id": project, "work_type_id": wt["id"], "base_marks": wt["base_marks"],
                  "proof_url": url, "proof_key": key, "note": note, "minutes": minutes,
                  "log_date": log_date, "late": 1 if log_date < today else 0}


def create_log(user, body):
    g = _guard(user, "tracker", write=True)
    if g:
        return g
    _seen(user)
    cfg = store.get_settings()
    err, f = _check_log(user, body or {}, cfg)
    if err:
        return err
    cur = store.write(
        "INSERT INTO daily_logs(user_id, user_name, user_email, project_id, work_type_id, base_marks, "
        "proof_url, proof_key, note, minutes, log_date, submitted_at, late, status, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'submitted','manual')",
        (uid(user), user.get("name") or "", (user.get("email") or "").lower(), f["project_id"],
         f["work_type_id"], f["base_marks"], f["proof_url"], f["proof_key"], f["note"],
         f["minutes"], f["log_date"], store.now_iso(), f["late"]))
    known, _ = sites(user)
    r = store.one("SELECT * FROM daily_logs WHERE id=?", (cur.lastrowid,))
    return 201, {"log": _public_log(r, _types(), known),
                 "late": bool(f["late"]),
                 "message": ("Logged. It was submitted after the day, so it earns half marks once approved."
                             if f["late"] else "Logged — it counts once Jai approves it.")}


def update_log(user, log_id, body):
    """Fix a log that is still waiting, or one sent back as "needs fix"."""
    g = _guard(user, "tracker", write=True)
    if g:
        return g
    r = store.one("SELECT * FROM daily_logs WHERE id=?", (log_id,))
    if not r or r["user_id"] != uid(user):
        return 404, {"error": "not_found", "message": "That log is not yours or no longer exists."}
    if r["status"] not in ("submitted", "needs_fix"):
        return _bad("Only a log that is waiting or sent back can be changed.")
    merged = {"project_id": r["project_id"], "work_type_id": r["work_type_id"],
              "proof_url": r["proof_url"], "note": r["note"], "minutes": r["minutes"],
              "date": r["log_date"]}
    merged.update({k: v for k, v in (body or {}).items() if v is not None})
    err, f = _check_log(user, merged, store.get_settings(), exclude_id=log_id)
    if err:
        return err
    # A fix keeps the original "late" verdict: re-submitting is not being late.
    late = r["late"] if f["log_date"] == r["log_date"] else f["late"]
    store.write("UPDATE daily_logs SET project_id=?, work_type_id=?, base_marks=?, proof_url=?, "
                "proof_key=?, note=?, minutes=?, log_date=?, late=?, status='submitted', "
                "marks_awarded=0, quality=NULL WHERE id=?",
                (f["project_id"], f["work_type_id"], f["base_marks"], f["proof_url"], f["proof_key"],
                 f["note"], f["minutes"], f["log_date"], late, log_id))
    known, _ = sites(user)
    return 200, {"log": _public_log(store.one("SELECT * FROM daily_logs WHERE id=?", (log_id,)),
                                    _types(), known)}


def delete_log(user, log_id):
    g = _guard(user, "tracker", write=True)
    if g:
        return g
    r = store.one("SELECT * FROM daily_logs WHERE id=?", (log_id,))
    if not r or r["user_id"] != uid(user):
        return 404, {"error": "not_found", "message": "That log is not yours or no longer exists."}
    if r["status"] != "submitted":
        return _bad("A reviewed log can't be removed.")
    store.write("DELETE FROM daily_logs WHERE id=?", (log_id,))
    return 200, {"deleted": log_id}


def list_logs(user, date=None, project_id=None, user_id=None):
    g = _guard(user, "tracker")
    if g:
        return g
    admin = is_admin(user)
    known, allowed = sites(user)
    date = (date or store.today_ist())[:10]
    sql, args = "SELECT * FROM daily_logs WHERE log_date=?", [date]
    # Reviewers may pass user_id=<id> for one person or user_id=all for everyone.
    who = uid(user)
    if admin and user_id:
        who = None if str(user_id) == "all" else str(user_id)
    if who:
        sql += " AND user_id=?"
        args.append(str(who))
    if project_id:
        sql += " AND project_id=?"
        args.append(project_id)
    types = _types()
    logs = [_public_log(r, types, known) for r in store.rows(sql + " ORDER BY submitted_at", args)]
    # Backlink Ops rows for the same person and day — shown, never re-entered.
    if who == uid(user):
        names = [user.get("name")]
    elif who:
        names = [p["name"] for p in store.rows("SELECT name FROM dt_people WHERE user_id=?", (who,))]
    else:
        names = [p["name"] for p in store.rows("SELECT name FROM dt_people")]
    # One row per person and site: 40 links a day would bury everything else.
    bt = _backlink_type()
    groups = {}
    for b in backlink_rows(names, date, date):
        if project_id and b["project"] != project_id:
            continue
        g = groups.setdefault((_norm_name(b["author"]), b["project"]),
                              {"author": b["author"], "project": b["project"], "n": 0,
                               "approved": 0, "pending": 0, "back": 0})
        g["n"] += 1
        g["approved" if b["status"] == "approved" else
          "pending" if b["status"] == "pending" else "back"] += 1
    for (who_, p), g in groups.items():
        bits = [f"{g['approved']} approved", f"{g['pending']} waiting"] + \
               ([f"{g['back']} sent back"] if g["back"] else [])
        logs.append({"id": f"bo:{who_}:{p}", "userName": g["author"], "project": p,
                     "site": (known.get(p) or {}).get("short", p),
                     "workType": f"{(bt or {}).get('name', 'Backlink built')} × {g['n']}",
                     "proofUrl": "/seo/backlink-ops/",
                     "note": "Backlink Ops · " + " · ".join(bits), "date": date,
                     "status": "approved" if not g["pending"] and not g["back"] else "submitted",
                     "source": "backlink_ops", "late": False, "marks": None, "count": g["n"]})
    return 200, {"date": date, "logs": logs}


# ------------------------------------------------------------------ review
def _review_one(reviewer, r, status, quality, note, cfg):
    if status == "approved":
        q = int(quality or 3)
        if q not in QUALITY:
            return _bad("Quality is 1 to 5.")
        marks = marks_for(r["base_marks"], q, r["late"], cfg)
    else:
        q, marks = (int(quality) if quality else None), 0.0
    store.write("UPDATE daily_logs SET status=?, quality=?, marks_awarded=?, reviewer_id=?, "
                "reviewer_name=?, reviewed_at=?, review_note=? WHERE id=?",
                (status, q, marks, uid(reviewer), reviewer.get("name") or "", store.now_iso(),
                 str(note or "")[:300], r["id"]))
    return None


def review(user, log_id, body):
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    body = body or {}
    st = body.get("status")
    if st not in ("approved", "needs_fix", "rejected"):
        return _bad("Status must be approved, needs_fix or rejected.")
    r = store.one("SELECT * FROM daily_logs WHERE id=?", (log_id,))
    if not r:
        return 404, {"error": "not_found", "message": "No such log."}
    err = _review_one(user, r, st, body.get("quality"), body.get("note"), store.get_settings())
    if err:
        return err
    known, _ = sites(user)
    return 200, {"log": _public_log(store.one("SELECT * FROM daily_logs WHERE id=?", (log_id,)),
                                    _types(), known)}


def review_bulk(user, body):
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    body = body or {}
    ids, st = body.get("ids"), body.get("status")
    if not isinstance(ids, list) or not ids:
        return _bad("Pick at least one log.")
    if st not in ("approved", "needs_fix", "rejected"):
        return _bad("Status must be approved, needs_fix or rejected.")
    cfg, done = store.get_settings(), 0
    for i in ids:
        r = store.one("SELECT * FROM daily_logs WHERE id=?", (int(i),))
        if r and not _review_one(user, r, st, body.get("quality"), body.get("note"), cfg):
            done += 1
    return 200, {"reviewed": done}


def review_queue(user):
    if not user:
        return ERR_AUTH
    if not is_admin(user):
        return ERR_ADMIN
    out = {"logs": [], "ideas": []}
    known, _ = sites(user)
    if settings.TRACKER:
        types = _types()
        out["logs"] = [_public_log(r, types, known) for r in store.rows(
            "SELECT * FROM daily_logs WHERE status='submitted' ORDER BY log_date, submitted_at")]
    if settings.IDEAS:
        out["ideas"] = _ideas_rows("WHERE i.status IN ('new','shortlisted','in_trial')", (), user)
    return 200, out


# ------------------------------------------------------------------ totals
def totals(people, d_from, d_to, cfg):
    """{(user_id, project, date): {marks, approved, pending, needs_fix, bo_links, bo_marks}}
    for these people ({user_id: name}). Backlink Ops marks are capped per person per day."""
    out = {}

    def cell(k):
        return out.setdefault(k, {"marks": 0.0, "approved": 0, "pending": 0, "needs_fix": 0,
                                  "bo_links": 0, "bo_pending": 0, "bo_marks": 0.0})

    if not people:
        return out
    marks = "(%s)" % ",".join("?" * len(people))
    for r in store.rows("SELECT user_id, project_id, log_date, status, marks_awarded FROM daily_logs "
                        "WHERE log_date BETWEEN ? AND ? AND user_id IN " + marks,
                        [d_from, d_to] + list(people)):
        c = cell((r["user_id"], r["project_id"], r["log_date"]))
        if r["status"] == "approved":
            c["approved"] += 1
            c["marks"] = round(c["marks"] + r["marks_awarded"], 2)
        elif r["status"] == "submitted":
            c["pending"] += 1
        elif r["status"] == "needs_fix":
            c["needs_fix"] += 1

    bt = _backlink_type()
    per_link = float(bt["base_marks"]) if bt and bt["active"] else 0.0
    cap = float(cfg.get("backlink_daily_cap", 0) or 0)
    by_name = {_norm_name(n): u for u, n in people.items()}
    for b in backlink_rows(list(people.values()), d_from, d_to):
        u = by_name.get(_norm_name(b["author"]))
        c = cell((u, b["project"], b["date"]))
        if b["status"] == "approved":
            c["bo_links"] += 1
        elif b["status"] in ("pending",):
            c["bo_pending"] += 1
    # the cap applies per person per DAY across sites
    day_bo = {}
    for (u, p, d), c in out.items():
        day_bo.setdefault((u, d), []).append(c)
    for (u, d), cells in day_bo.items():
        budget = cap
        for c in cells:
            want = c["bo_links"] * per_link
            give = min(want, max(0.0, budget))
            budget -= give
            c["bo_marks"] = round(give, 2)
            c["marks"] = round(c["marks"] + give, 2)
    return out


def _per_day(cells, user_id):
    day = {}
    for (u, p, d), c in cells.items():
        if u != user_id:
            continue
        x = day.setdefault(d, {"marks": 0.0, "approved": 0, "pending": 0, "needs_fix": 0,
                               "bo_links": 0, "bo_pending": 0, "bo_marks": 0.0})
        for k in x:
            x[k] = round(x[k] + c[k], 2) if isinstance(x[k], float) else x[k] + c[k]
    return day


def _streak(hit_days, today):
    n, d = 0, _date.fromisoformat(today)
    if today not in hit_days:
        d -= timedelta(days=1)
    while d.isoformat() in hit_days:
        n += 1
        d -= timedelta(days=1)
    return n


def summary(user, rng="day", user_id=None):
    g = _guard(user, "tracker")
    if g:
        return g
    _seen(user)
    cfg = store.get_settings()
    today = store.today_ist()
    me = str(user_id) if (user_id and is_admin(user)) else uid(user)
    person = store.one("SELECT * FROM dt_people WHERE user_id=?", (me,)) or \
        {"user_id": me, "name": user.get("name")}
    d_from, d_to = _range(rng if rng in ("day", "week", "month") else "day", today)
    # Heatmap and streak need history either way: the whole month plus 60 days.
    h_from = min(d_from, (_date.fromisoformat(today) - timedelta(days=60)).isoformat())
    cells = totals({me: person["name"]}, h_from, today, cfg)
    per = _per_day(cells, me)
    target = store.target_for(me, today, cfg["default_daily_target"])
    hit = {d for d, x in per.items() if x["marks"] >= store.target_for(me, d, cfg["default_daily_target"])}
    series = [{"date": d, "marks": (per.get(d) or {}).get("marks", 0.0),
               "target": store.target_for(me, d, cfg["default_daily_target"]),
               "hit": d in hit} for d in _days(d_from, d_to)]
    t = per.get(today) or {"marks": 0.0, "approved": 0, "pending": 0, "needs_fix": 0,
                           "bo_links": 0, "bo_pending": 0, "bo_marks": 0.0}
    month_from = _date.fromisoformat(today).replace(day=1).isoformat()
    _, ndays = monthrange(int(today[:4]), int(today[5:7]))
    heat = [{"date": d, "marks": (per.get(d) or {}).get("marks", 0.0), "hit": d in hit,
             "future": d > today}
            for d in _days(month_from, today[:8] + f"{ndays:02d}")]
    board = leaderboard(month_from, today, cfg)
    if not is_admin(user):                  # per-site boards only for your own sites
        _, allowed = sites(user)
        board["projects"] = {p: r for p, r in board["projects"].items() if p in allowed}
    return 200, {"range": rng, "from": d_from, "to": d_to, "today": today, "target": target,
                 "todayTotals": dict(t, done=t["marks"] >= target, items=t["approved"] + t["bo_links"]),
                 "series": series, "heatmap": heat, "streak": _streak(hit, today),
                 "rank": next((r["rank"] for r in board["overall"] if r["userId"] == me), None),
                 "projectRanks": {p: next((r["rank"] for r in rows if r["userId"] == me), None)
                                  for p, rows in board["projects"].items()},
                 "leaderboard": board,
                 "person": {"userId": me, "name": person["name"]}}


def leaderboard(d_from, d_to, cfg):
    people = {p["user_id"]: p["name"] for p in store.rows("SELECT user_id, name FROM dt_people")}
    cells = totals(people, d_from, d_to, cfg)
    overall, per_project = {}, {}
    for (u, p, d), c in cells.items():
        if not u:
            continue
        overall[u] = round(overall.get(u, 0.0) + c["marks"], 2)
        per_project.setdefault(p, {})
        per_project[p][u] = round(per_project[p].get(u, 0.0) + c["marks"], 2)

    def ranked(m):
        rows = sorted(({"userId": u, "name": people.get(u, u), "marks": v} for u, v in m.items()
                       if v > 0), key=lambda r: (-r["marks"], r["name"].lower()))
        for i, r in enumerate(rows):
            r["rank"] = i + 1 if i == 0 or r["marks"] < rows[i - 1]["marks"] else rows[i - 1]["rank"]
        return rows
    return {"from": d_from, "to": d_to, "overall": ranked(overall),
            "projects": {p: ranked(m) for p, m in per_project.items()}}


# ------------------------------------------------------------------ admin
def report(user, d_from=None, d_to=None):
    if not user:
        return ERR_AUTH
    if not is_admin(user):
        return ERR_ADMIN
    if not settings.TRACKER:
        return ERR_TRACKER_OFF
    cfg = store.get_settings()
    today = store.today_ist()
    d_to = (d_to or today)[:10]
    d_from = (d_from or _date.fromisoformat(d_to).replace(day=1).isoformat())[:10]
    if d_from > d_to:
        return _bad("'From' must be before 'to'.")
    people = {p["user_id"]: p for p in store.rows("SELECT * FROM dt_people ORDER BY lower(name)")}
    cells = totals({u: p["name"] for u, p in people.items()}, d_from, d_to, cfg)
    days = [d for d in _days(d_from, d_to) if d <= today]
    out = []
    for u, p in people.items():
        per = _per_day(cells, u)
        hit = sum(1 for d in days if (per.get(d) or {}).get("marks", 0) >=
                  store.target_for(u, d, cfg["default_daily_target"]))
        by_project = {}
        for (cu, proj, d), c in cells.items():
            if cu == u:
                x = by_project.setdefault(proj, {"marks": 0.0, "items": 0, "pending": 0})
                x["marks"] = round(x["marks"] + c["marks"], 2)
                x["items"] += c["approved"] + c["bo_links"]
                x["pending"] += c["pending"]
        out.append({"userId": u, "name": p["name"], "email": p["email"],
                    "marks": round(sum(x["marks"] for x in per.values()), 2),
                    "daysHit": hit, "days": len(days),
                    "pctHit": round(100 * hit / len(days)) if days else 0,
                    "target": store.target_for(u, today, cfg["default_daily_target"]),
                    "projects": by_project,
                    "badges": store.rows("SELECT month, idea_id FROM user_badges WHERE user_id=?", (u,))})
    return 200, {"from": d_from, "to": d_to, "people": out, "settings": cfg}


def export_csv(user, d_from=None, d_to=None):
    """(status, csv_text | error payload). Manual logs one per row; Backlink Ops
    links one row per person, site and day."""
    if not user:
        return ERR_AUTH
    if not is_admin(user):
        return ERR_ADMIN
    if not settings.TRACKER:
        return ERR_TRACKER_OFF
    today = store.today_ist()
    d_to = (d_to or today)[:10]
    d_from = (d_from or _date.fromisoformat(d_to).replace(day=1).isoformat())[:10]
    known, _ = sites(user)
    types = _types()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Person", "Email", "Project", "Work type", "Proof link", "Note", "Minutes",
                "Status", "Quality", "Marks", "Late", "Source", "Submitted at", "Reviewer"])
    for r in store.rows("SELECT * FROM daily_logs WHERE log_date BETWEEN ? AND ? "
                        "ORDER BY log_date, user_name, submitted_at", (d_from, d_to)):
        w.writerow([r["log_date"], r["user_name"], r["user_email"],
                    (known.get(r["project_id"]) or {}).get("domain") or r["project_id"],
                    (types.get(r["work_type_id"]) or {}).get("name", ""), r["proof_url"],
                    r["note"], r["minutes"], r["status"], r["quality"] or "", r["marks_awarded"],
                    "yes" if r["late"] else "", "manual", r["submitted_at"], r["reviewer_name"] or ""])
    people = {p["user_id"]: p["name"] for p in store.rows("SELECT user_id, name FROM dt_people")}
    cells = totals(people, d_from, d_to, store.get_settings())
    for (u, p, d), c in sorted(cells.items(), key=lambda kv: (kv[0][2], str(kv[0][0]))):
        if c["bo_links"] or c["bo_pending"]:
            w.writerow([d, people.get(u, u), "", (known.get(p) or {}).get("domain") or p,
                        "Backlink built", "", f"{c['bo_links']} approved, {c['bo_pending']} pending "
                        "in Backlink Ops", "", "approved" if c["bo_links"] else "submitted", "",
                        c["bo_marks"], "", "backlink_ops", "", ""])
    return 200, buf.getvalue()


def import_csv(user, body):
    """Continuity: work logged in the shared Google Sheet while the dashboard
    was down. Columns: Email, Project, Work type, Link, Note, Minutes, Date.
    Rows arrive as 'submitted' (not late) and go through review as usual."""
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    text = str((body or {}).get("csv") or "")
    if not text.strip():
        return _bad("Paste the sheet as CSV.")
    known, _ = sites(user)
    by_domain = {(v.get("domain") or "").lower(): k for k, v in known.items()}
    by_domain.update({k: k for k in known})
    types = {t["name"].lower(): t for t in store.rows("SELECT * FROM work_types")}
    added, skipped = 0, []
    for i, row in enumerate(csv.DictReader(io.StringIO(text.strip())), start=2):
        row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
        person = store.one("SELECT * FROM dt_people WHERE email=?", (row.get("email", "").lower(),))
        proj = by_domain.get(row.get("project", "").lower().removeprefix("www."))
        wt = types.get(row.get("work type", "").lower())
        url = row.get("link", "")
        why = (not person and "unknown email (they must open the tracker once)") or \
              (not proj and "unknown project") or (not wt and "unknown work type") or \
              (not _valid_url(url) and "link is not a web address") or None
        if not why and store.one("SELECT id FROM daily_logs WHERE proof_key=? AND status!='rejected'",
                                 (proof_key(url),)):
            why = "link already logged"
        try:
            d = _date.fromisoformat(row.get("date", "")[:10]).isoformat()
        except ValueError:
            d, why = None, why or "date must look like 2026-10-13"
        if why:
            skipped.append({"row": i, "why": why})
            continue
        try:
            minutes = max(0, min(1440, int(row.get("minutes") or 0)))
        except ValueError:
            minutes = 0
        store.write("INSERT INTO daily_logs(user_id, user_name, user_email, project_id, work_type_id, "
                    "base_marks, proof_url, proof_key, note, minutes, log_date, submitted_at, late, "
                    "status, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,'submitted','manual')",
                    (person["user_id"], person["name"], person["email"], proj, wt["id"],
                     wt["base_marks"], url, proof_key(url), row.get("note", "")[:NOTE_MAX], minutes,
                     d, store.now_iso()))
        added += 1
    return 200, {"added": added, "skipped": skipped}


def put_settings(user, body):
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    body = body or {}
    cfg = store.get_settings()
    for k, lo, hi in (("default_daily_target", 1, 1000), ("backlink_daily_cap", 0, 1000)):
        if k in body:
            try:
                cfg[k] = max(lo, min(hi, float(body[k])))
            except (TypeError, ValueError):
                return _bad(f"{k} must be a number.")
    store.put_settings(cfg, user.get("name") or "admin")
    return 200, cfg


def set_target(user, body):
    g = _guard(user, "tracker", write=True, admin=True)
    if g:
        return g
    body = body or {}
    who = str(body.get("user_id") or "")
    if not store.one("SELECT user_id FROM dt_people WHERE user_id=?", (who,)):
        return 404, {"error": "not_found", "message": "That person has not opened the tracker yet."}
    try:
        t = float(body.get("daily_marks_target"))
    except (TypeError, ValueError):
        return _bad("Target must be a number.")
    if not 1 <= t <= 1000:
        return _bad("Target must be between 1 and 1000 marks.")
    eff = str(body.get("effective_from") or store.today_ist())[:10]
    store.set_target(who, t, eff, user.get("name") or "admin")
    return 200, {"user_id": who, "daily_marks_target": t, "effective_from": eff}


# ------------------------------------------------------------------ ideas
def _ideas_rows(where, args, user):
    me = uid(user)
    rs = store.rows("SELECT i.*, (SELECT COUNT(*) FROM idea_votes v WHERE v.idea_id=i.id) votes, "
                    "(SELECT COUNT(*) FROM idea_votes v WHERE v.idea_id=i.id AND v.user_id=?) mine "
                    "FROM ideas i " + where + " ORDER BY i.created_at DESC", (me,) + tuple(args))
    known, _ = sites(user)
    for r in rs:
        r["site"] = (known.get(r["project_id"]) or {}).get("short", r["project_id"])
        r["votedByMe"] = bool(r.pop("mine"))
        r["isMine"] = r["user_id"] == me
    return rs


def list_ideas(user, project_id=None, status=None, month=None):
    g = _guard(user, "ideas")
    if g:
        return g
    _seen(user)
    known, allowed = sites(user)
    vis = list(known) if is_admin(user) else allowed
    if not vis:
        return 200, {"ideas": [], "statuses": IDEA_STATUSES}
    where = "WHERE i.project_id IN (%s)" % ",".join("?" * len(vis))
    args = list(vis)
    if project_id:
        where += " AND i.project_id=?"
        args.append(project_id)
    if status in IDEA_STATUSES:
        where += " AND i.status=?"
        args.append(status)
    if month:
        where += " AND i.month_won=?"
        args.append(month[:7])
    winners = store.rows("SELECT b.month, b.user_name, b.idea_id FROM user_badges b "
                         "ORDER BY b.month DESC LIMIT 24")
    return 200, {"ideas": _ideas_rows(where, args, user), "statuses": IDEA_STATUSES,
                 "winners": winners}


def create_idea(user, body):
    g = _guard(user, "ideas", write=True)
    if g:
        return g
    _seen(user)
    body = body or {}
    _, allowed = sites(user)
    project = str(body.get("project_id") or "")
    if project not in allowed:
        return _bad("Pick one of your sites.")
    f = {k: str(body.get(k) or "").strip() for k in
         ("title", "problem", "idea", "expected_result", "metric")}
    if len(f["title"]) < 4:
        return _bad("Give the idea a short title.")
    if len(f["idea"]) < 10:
        return _bad("Describe the idea in a sentence or two.")
    if len(f["title"]) > 140 or any(len(v) > 2000 for v in f.values()):
        return _bad("Keep the title under 140 characters and each box under 2000.")
    now = store.now_iso()
    cur = store.write("INSERT INTO ideas(user_id, user_name, project_id, title, problem, idea, "
                      "expected_result, metric, status, created_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?,?,'new',?,?)",
                      (uid(user), user.get("name") or "", project, f["title"], f["problem"],
                       f["idea"], f["expected_result"], f["metric"], now, now))
    return 201, {"idea": _ideas_rows("WHERE i.id=?", (cur.lastrowid,), user)[0]}


def idea_status(user, idea_id, body):
    g = _guard(user, "ideas", write=True, admin=True)
    if g:
        return g
    body = body or {}
    st = body.get("status")
    if st not in IDEA_STATUSES:
        return _bad("Unknown status.")
    i = store.one("SELECT * FROM ideas WHERE id=?", (idea_id,))
    if not i:
        return 404, {"error": "not_found", "message": "No such idea."}
    note = str(body.get("result_note") or i["result_note"] or "").strip()[:2000]
    if st == "worked" and len(note) < 3:
        return _bad("Say what it achieved (e.g. +X traffic, +Y leads) before marking it Worked.")
    month = None
    if st == "worked":
        month = str(body.get("month") or store.today_ist())[:7]
        store.write("INSERT OR IGNORE INTO user_badges(user_id, user_name, month, kind, idea_id, created_at) "
                    "VALUES (?,?,?,'idea_winner',?,?)",
                    (i["user_id"], i["user_name"], month, idea_id, store.now_iso()))
    else:
        store.write("DELETE FROM user_badges WHERE idea_id=? AND kind='idea_winner'", (idea_id,))
    store.write("UPDATE ideas SET status=?, result_note=?, month_won=?, decided_by=?, updated_at=? "
                "WHERE id=?", (st, note, month, user.get("name") or "admin", store.now_iso(), idea_id))
    return 200, {"idea": _ideas_rows("WHERE i.id=?", (idea_id,), user)[0]}


def vote(user, idea_id):
    g = _guard(user, "ideas", write=True)
    if g:
        return g
    i = store.one("SELECT * FROM ideas WHERE id=?", (idea_id,))
    known, allowed = sites(user)
    if not i or (not is_admin(user) and i["project_id"] not in allowed):
        return 404, {"error": "not_found", "message": "No such idea."}
    if i["user_id"] == uid(user):
        return _bad("You can't vote for your own idea.")
    if store.one("SELECT 1 x FROM idea_votes WHERE idea_id=? AND user_id=?", (idea_id, uid(user))):
        store.write("DELETE FROM idea_votes WHERE idea_id=? AND user_id=?", (idea_id, uid(user)))
    else:
        store.write("INSERT INTO idea_votes(idea_id, user_id, voted_at) VALUES (?,?,?)",
                    (idea_id, uid(user), store.now_iso()))
    return 200, {"idea": _ideas_rows("WHERE i.id=?", (idea_id,), user)[0]}
