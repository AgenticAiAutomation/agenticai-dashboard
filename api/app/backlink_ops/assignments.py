"""Backlink Ops — who is assigned to which website.

The roster (Difficulty & team → Team & assignments) is the one place a person
is put on a site. Before v1.3 the desk matched a roster row to the signed-in
person with an exact, case-sensitive compare of the display name, in the
browser — so "Akash" on the roster never matched the login "Akash Yadav", and
a site marked "not live" was hidden even from the person rostered on it.

Rules now, in one place, used by the desk, the per-site levels and the Daily
Tracker alike:

  * A roster row matches a user by email (case and spaces ignored), else by
    full name (same), else by the email typed into the Name box.
  * One person may have several rows — one per site. Each row is a site.
  * A site is visible to a user if it is live, OR they are rostered on it,
    OR they are the superuser.
"""
from .identity import is_superuser
from .seed import projects as projects_of


def norm(value):
    return " ".join(str(value or "").split()).lower()


def roster_rows_for(user, cfg):
    if not user:
        return []
    email, name = norm(user.get("email")), norm(user.get("name"))
    out = []
    for r in (cfg or {}).get("roster") or []:
        r_email, r_name = norm(r.get("email")), norm(r.get("name"))
        if (email and r_email and r_email == email) \
                or (name and r_name and r_name == name) \
                or (email and r_name and r_name == email):
            out.append(r)
    return out


def assigned_projects(user, cfg):
    """Project ids this user is rostered on, roster order, no repeats."""
    known = projects_of(cfg)
    seen = []
    for r in roster_rows_for(user, cfg):
        p = r.get("project")
        if p in known and p not in seen:
            seen.append(p)
    return seen


def visible_projects(user, cfg):
    known = projects_of(cfg)
    if is_superuser(user):
        return list(known)
    mine = set(assigned_projects(user, cfg))
    return [pid for pid, p in known.items() if p.get("active") is not False or pid in mine]


def unmatched_roster(cfg, seen_users):
    """Roster rows nobody has signed in as yet. `seen_users` is the list of
    {name, email} the desk has met (from the level table). A row stuck here
    means the name/email typed on the roster does not match any login —
    exactly the T1 symptom, made visible to the superuser."""
    out = []
    for r in (cfg or {}).get("roster") or []:
        if r.get("owner"):
            continue
        if not any(roster_rows_for(u, {"roster": [r]}) for u in seen_users):
            out.append({"name": r.get("name"), "email": r.get("email") or "",
                        "project": r.get("project")})
    return out
