"""Backlink Ops — the whole feature, with no web framework in sight.

Every function takes the resolved user (or None) plus plain arguments, and
returns `(http_status, payload_dict)`. The Flask and FastAPI adapters are thin
translators around these; all policy — who may do what, what counts as valid
input, what gets audited — lives here, once, so the two adapters cannot drift
apart.

Adding an endpoint: write the function here, wire it in BOTH adapters, document
it in docs/API.md.
"""
import json
import uuid

from . import ai, audit, levels, store
from .assignments import assigned_projects, norm, unmatched_roster, visible_projects
from .config import settings
from .identity import can_write, is_superuser
from .scoring import day_stats, host_of
from .seed import (DEFAULT_CONFIG, LEVELS, LEVEL_EDITABLE, LINK_TYPES, TYPE_MAP,
                   level as level_for, levels as levels_of, projects as projects_of,
                   seed_keywords, site_level)

# --------------------------------------------------------------- guards
ERR_AUTH = (401, {"error": "not_authenticated",
                  "message": "Sign in to the dashboard first."})
ERR_FORBID = (403, {"error": "forbidden",
                    "message": "Only the superuser can do that."})
ERR_READONLY = (403, {"error": "read_only_user",
                      "message": "Your dashboard account has view-only access to the desk."})
ERR_FROZEN = (503, {"error": "read_only",
                    "message": "The desk is in read-only mode while maintenance runs. "
                               "Your work is safe — try again shortly."})


def _writable(user):
    if not user:
        return ERR_AUTH
    if settings.READ_ONLY:
        return ERR_FROZEN
    if not can_write(user):
        return ERR_READONLY
    return None


def _super(user):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    if settings.READ_ONLY:
        return ERR_FROZEN
    return None


def _bad(message):
    return 400, {"error": "invalid", "message": message}


def _project(value):
    p = str(value or "agenticai").strip().lower()
    return p if p in projects_of(store.get_config()) else "agenticai"


def _stats(project, date, user=None):
    cfg = store.get_config()
    st = day_stats(store.entries_for(project, date),
                   store.decisions_for(project, date),
                   store.queries_for(project, date),
                   site_level(project, cfg), project, store.bank_keywords(project), cfg)
    # v1.3: the person's own day at their own level, beside the site view.
    # The site view (rows, review queue) is unchanged.
    # The superuser reviews rather than logs, so gets no level of their own.
    if settings.PER_PROJECT_LEVELS and user and not is_superuser(user):
        st["mine"] = levels.my_day(user, project, date, cfg)
    return st


# --------------------------------------------------------------- health
def health():
    ok = store.integrity_ok()
    return (200 if ok else 503), {
        "feature": "backlink-ops", "version": settings.VERSION,
        "schema": store.schema_version(), "enabled": settings.ENABLED,
        "read_only": settings.READ_ONLY, "db": store.db_path(), "db_ok": ok,
        "ai": ("configured" if ai.available() else "rules-only"),
        "ai_provider": settings.AI_PROVIDER,
        "ai_model": settings.AI_MODEL or "(provider default)",
        "ai_calls_today": store.ai_calls_today(),
    }


# --------------------------------------------------------------- bootstrap
def bootstrap(user, project=None):
    if not user:
        return ERR_AUTH
    cfg = store.get_config()
    assigned = assigned_projects(user, cfg)
    return 200, {
        "me": user, "config": cfg, "levels": levels_of(cfg),
        "level": level_for(site_level(_project(project or (assigned[0] if assigned else None)), cfg), cfg),
        "linkTypes": LINK_TYPES,
        "siteLevels": {p: site_level(p, cfg) for p in projects_of(cfg)},
        "projects": projects_of(cfg),
        "seedKeywords": {p: seed_keywords(p, cfg) for p in projects_of(cfg)},
        "autoReview": store.get_meta("autoreview_last") if is_superuser(user) else None,
        "today": store.today_ist(), "readOnly": settings.READ_ONLY or not can_write(user),
        "aiEnabled": ai.available(), "version": settings.VERSION,
        "project": _project(project or (assigned[0] if assigned else None)),
        "assigned": assigned, "visible": visible_projects(user, cfg),
        "perProjectLevels": settings.PER_PROJECT_LEVELS,
    }


def day(user, project=None, date=None):
    if not user:
        return ERR_AUTH
    p, d = _project(project), (date or store.today_ist())
    st = _stats(p, d, user)
    st.update({"project": p, "date": d,
               "coach": store.get_coach(p, d, user.get("name", ""))})
    return 200, st


# --------------------------------------------------------------- entries
def add_entry(user, body):
    guard = _writable(user)
    if guard:
        return guard
    body = body or {}
    project = _project(body.get("project"))
    url = str(body.get("url") or "").strip()
    if not url:
        return _bad("Paste the URL where you submitted the link.")
    if body.get("type") not in TYPE_MAP:
        return _bad("Pick a link type from the list.")
    try:
        da, spam = float(body.get("da") or 0), float(body.get("spam") or 0)
    except (TypeError, ValueError):
        return _bad("DA and spam score must be numbers.")

    e = {"id": "e" + uuid.uuid4().hex[:12], "project": project,
         "date": store.today_ist(), "author": user.get("name", "unknown"),
         "url": url, "host": host_of(url), "type": body["type"],
         "da": da, "spam": spam, "follow": body.get("follow") or "unknown",
         "target": str(body.get("target") or "").strip(),
         "anchor": str(body.get("anchor") or "").strip(),
         "kw": str(body.get("kw") or "").strip(),
         "relevant": 1 if body.get("relevant") else 0,
         "indexed": 1 if body.get("indexed") else 0,
         "created_at": store.now_iso()}
    store.add_entry(e)
    audit.stamp_user(user, "entry.add", target=e["id"],
                     detail={"project": project, "host": e["host"],
                             "type": e["type"], "da": e["da"]})
    return 201, _stats(project, e["date"], user)


def delete_entry(user, entry_id, project=None):
    guard = _writable(user)
    if guard:
        return guard
    p = _project(project)
    if not store.delete_entry(entry_id, p):
        return 404, {"error": "not_found", "message": "That link is no longer on the sheet."}
    audit.stamp_user(user, "entry.delete", target=entry_id, detail={"project": p})
    return 200, _stats(p, store.today_ist(), user)


# --------------------------------------------------------------- keyword lab
def analyse(user, body):
    guard = _writable(user)
    if guard:
        return guard
    body = body or {}
    project = _project(body.get("project"))
    kw = str(body.get("kw") or "").strip()
    pasted = str(body.get("pasted") or "")
    skip = bool(body.get("skip"))
    if not kw:
        return _bad("No keyword to analyse.")
    if not skip and len(pasted.strip()) < 8:
        return _bad("Paste the Ubersuggest numbers first.")

    if skip:
        out = {"verdict": "drop", "why": "Skipped without data.", "volume": None,
               "kd": None, "cpc": None, "targetPage": "", "anchors": [],
               "linkPlan": [], "nextFocus": "", "_source": "skip"}
    else:
        out = ai.keyword_verdict(project, kw, pasted)

    now = store.now_iso()
    store.upsert_bank({"project": project, "kw": kw, "volume": out.get("volume"),
                       "kd": out.get("kd"), "cpc": out.get("cpc"),
                       "verdict": out.get("verdict"), "why": out.get("why"),
                       "target_page": out.get("targetPage"),
                       "anchors": json.dumps(out.get("anchors") or []),
                       "link_plan": json.dumps(out.get("linkPlan") or []),
                       "author": user.get("name", "unknown"), "updated_at": now})
    store.add_query({"id": "q" + uuid.uuid4().hex[:12], "project": project,
                     "date": store.today_ist(), "author": user.get("name", "unknown"),
                     "kw": kw, "volume": out.get("volume"), "kd": out.get("kd"),
                     "cpc": out.get("cpc"), "verdict": out.get("verdict"),
                     "why": out.get("why"), "raw": pasted[:8000],
                     "source": "ubersuggest", "created_at": now})
    audit.stamp_user(user, "keyword.analyse", target=kw,
                     detail={"project": project, "verdict": out.get("verdict"),
                             "engine": out.get("_source")})
    return 200, {"analysis": out, "day": _stats(project, store.today_ist(), user),
                 "bank": store.bank_for(project)}


def bank(user, project=None):
    if not user:
        return ERR_AUTH
    p = _project(project)
    return 200, {"project": p, "keywords": store.bank_for(p)}


# --------------------------------------------------------------- coach
def coach(user, body):
    guard = _writable(user)
    if guard:
        return guard
    project = _project((body or {}).get("project"))
    date = store.today_ist()
    st = _stats(project, date)
    if not st["rows"]:
        return 400, {"error": "empty",
                     "message": "Log some links first — there is nothing to review."}
    out = ai.coach(project, st, st["level"])
    store.put_coach(project, date, user.get("name", ""), out)
    audit.stamp_user(user, "coach.run", target=project,
                     detail={"grade": out.get("grade"), "engine": out.get("_source")})
    return 200, {"coach": out}


# --------------------------------------------------------------- review
def review(user, body):
    guard = _super(user)
    if guard:
        return guard
    body = body or {}
    project = _project(body.get("project"))
    decisions = body.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return _bad("Nothing to review.")
    allowed = {"approved", "rejected", "needs_fix", "pending"}
    for d in decisions:
        if not isinstance(d, dict) or d.get("status") not in allowed:
            return _bad(f"Unknown status {(d or {}).get('status')!r}.")
        if not d.get("id"):
            return _bad("A decision arrived without a link id.")
    for d in decisions:
        store.set_decision(d["id"], d["status"], d.get("note"),
                           user.get("name", "superuser"))
    audit.stamp_user(user, "review.decide", target=project,
                     detail={"count": len(decisions),
                             "statuses": sorted({d["status"] for d in decisions})})
    return 200, _stats(project, store.today_ist())


# --------------------------------------------------------------- scoreboard
def board(user, days=14):
    if not user:
        return ERR_AUTH
    try:
        days_back = min(max(int(days), 1), 90)
    except (TypeError, ValueError):
        days_back = 14
    points, queries = store.history(days_back)
    cfg = store.get_config()
    L = level_for(cfg.get("level", 1), cfg)
    lv = _pair_level(cfg)
    series = []
    for (a, p, d), v in points.items():
        Lp = lv(a, p)
        series.append({"author": a, "project": p, "date": d, "points": v,
                       "queries": queries.get((a, p, d), 0), "level": Lp["n"],
                       "target": Lp["target"],
                       "done": v >= Lp["target"] and queries.get((a, p, d), 0) >= Lp["queries"]})
    return 200, {"series": series, "level": L,
                 "roster": cfg.get("roster", DEFAULT_CONFIG["roster"]),
                 "bankCounts": {p: len(store.bank_for(p)) for p in projects_of(cfg)},
                 "days": days_back, "today": store.today_ist()}


# --------------------------------------------------------------- all projects (v1.2)
def progress(user, days=14):
    """Daily progress across EVERY project — not just the one each associate
    is rostered on. The scoreboard answers "is this person on target"; this
    answers "what happened on each website today, and who did it"."""
    if not user:
        return ERR_AUTH
    try:
        days_back = min(max(int(days), 1), 90)
    except (TypeError, ValueError):
        days_back = 14
    cfg = store.get_config()
    L = level_for(cfg.get("level", 1), cfg)
    lv = _pair_level(cfg)
    rows = []
    for (p, d, a), c in store.progress(days_back).items():
        c = dict(c)
        Lp = lv(a, p)
        c.update({"project": p, "date": d, "author": a, "level": Lp["n"], "target": Lp["target"],
                  "done": (c["points"] >= Lp["target"]
                           and (c["links"] - c["rejected"]) >= Lp.get("min_links", 0)
                           and c["queries"] >= Lp["queries"])})
        rows.append(c)
    rows.sort(key=lambda r: (r["date"], r["project"], r["author"]))
    return 200, {"rows": rows, "level": L, "days": days_back,
                 "today": store.today_ist(), "projects": projects_of(cfg),
                 "visible": visible_projects(user, cfg),
                 "roster": cfg.get("roster", DEFAULT_CONFIG["roster"])}


def _pair_level(cfg):
    """Level for an (author name, site) pair: their own when per-site levels
    are on and the desk has met them, else the global level as before."""
    site = {p: level_for(site_level(p, cfg), cfg) for p in projects_of(cfg)}
    g = level_for(cfg.get("level", 1), cfg)
    if not settings.PER_PROJECT_LEVELS:
        return lambda author, project: site.get(project, g)        # v1.4: per website
    table = levels.level_lookup(cfg)

    def lookup(author, project):
        n = table.get((norm(author), project))
        return level_for(n, cfg) if n else site.get(project, g)
    return lookup


# --------------------------------------------------------------- levels (v1.3)
ERR_LEVELS_OFF = (404, {"error": "disabled",
                        "message": "Per-site levels are not switched on yet."})


def my_levels(user):
    """One row per site this person is on: level, today's progress, streak.
    Feeds the homepage "My Levels" card."""
    if not user:
        return ERR_AUTH
    if not settings.PER_PROJECT_LEVELS:
        return ERR_LEVELS_OFF
    cfg = store.get_config()
    known = projects_of(cfg)
    # The superuser reviews rather than logs: no level rows are made for them.
    sites = [] if is_superuser(user) else assigned_projects(user, cfg)
    uid = levels.user_key(user)
    for r in store.all_levels():          # sites they worked on without a roster row
        if r["user_id"] == uid and r["project_id"] in known and r["project_id"] not in sites:
            sites.append(r["project_id"])
    rows = []
    for p in sites:
        row = store.get_level(uid, p) if is_superuser(user) else levels.ensure(user, p, cfg)
        out = levels.refresh(row, cfg)
        out.update({"site": known[p].get("short") or p, "domain": known[p].get("domain", ""),
                    "hue": known[p].get("hue", "#5B6B68")})
        rows.append(out)
    return 200, {"me": {"name": user.get("name"), "email": user.get("email"),
                        "role": user.get("role")},
                 "rows": rows, "today": store.today_ist(), "readyAfter": levels.READY_STREAK}


def all_levels(user):
    """Superuser grid: every person x every site the desk has met, plus roster
    rows that match no login yet (the T1 symptom, made visible)."""
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    if not settings.PER_PROJECT_LEVELS:
        return ERR_LEVELS_OFF
    cfg = store.get_config()
    known = projects_of(cfg)
    rows = [levels.refresh(r, cfg) for r in store.all_levels() if r["project_id"] in known]
    seen = [{"name": r["name"], "email": r["email"]} for r in rows]
    return 200, {"rows": rows, "levels": levels_of(cfg),
                 "projects": {k: {"short": v.get("short"), "hue": v.get("hue"),
                                  "active": v.get("active") is not False} for k, v in known.items()},
                 "unmatched": unmatched_roster(cfg, seen),
                 "migration": store.get_meta("levels_v2_migration"),
                 "today": store.today_ist(), "readyAfter": levels.READY_STREAK}


def set_pair_level(user, body):
    guard = _super(user)
    if guard:
        return guard
    if not settings.PER_PROJECT_LEVELS:
        return ERR_LEVELS_OFF
    body = body or {}
    cfg = store.get_config()
    uid, project = str(body.get("userId") or ""), str(body.get("project") or "")
    if not store.get_level(uid, project):
        return 404, {"error": "not_found", "message": "That person has not worked on that site yet."}
    if body.get("reset") or body.get("level") in (None, "", "site"):
        lv = None                                     # follow the website's level again
    else:
        try:
            lv = int(body.get("level"))
        except (TypeError, ValueError):
            return _bad("Level must be a number from 1 to 5.")
        if not 1 <= lv <= len(LEVELS):
            return _bad(f"Level must be between 1 and {len(LEVELS)}.")
    row = levels.set_level(uid, project, lv, cfg)
    audit.stamp_user(user, "level.set", target=f"{uid}:{project}",
                     detail={"level": lv, "name": row["user_name"]})
    return 200, levels.refresh(row, cfg)


# --------------------------------------------------------------- websites (v1.4)
def set_site_level(user, body):
    """Difficulty for ONE website. Everyone on it follows this level unless
    Jai has set their own (Levels by person and site)."""
    guard = _super(user)
    if guard:
        return guard
    body = body or {}
    cfg = store.get_config()
    pid = str(body.get("project") or "")
    if pid not in projects_of(cfg):
        return _bad("Unknown website.")
    try:
        lv = int(body.get("level"))
    except (TypeError, ValueError):
        return _bad("Level must be a number from 1 to 5.")
    if not 1 <= lv <= len(LEVELS):
        return _bad(f"Level must be between 1 and {len(LEVELS)}.")
    plist = [dict(x) for x in cfg.get("projects") or [] if isinstance(x, dict)]
    row = next((x for x in plist if x.get("id") == pid), None)
    if row is None:
        plist.append({"id": pid, "level": lv})
    else:
        row["level"] = lv
    cfg["projects"] = plist
    store.put_config(cfg, user.get("name", "superuser"))
    audit.stamp_user(user, "site.level", target=pid, detail={"level": lv})
    return 200, {"project": pid, "level": lv, "siteLevels": {p: site_level(p, cfg) for p in projects_of(cfg)}}


def add_project(user, body):
    """One form: a new website, who works on it, and its level."""
    guard = _super(user)
    if guard:
        return guard
    body = body or {}
    cfg = store.get_config()
    name = str(body.get("name") or "").strip()[:80]
    domain = str(body.get("domain") or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").split("/")[0].removeprefix("www.")
    if len(name) < 2 or "." not in domain or " " in domain:
        return _bad("A new project needs a name and a domain like example.com.")
    if any((p.get("domain") or "").lower() == domain for p in projects_of(cfg).values()):
        return _bad(f"{domain} is already on the desk.")
    base = "".join(ch for ch in domain.split(".")[0] if ch.isalnum())[:24] or "site"
    pid, n = base, 2
    while pid in projects_of(cfg):
        pid, n = f"{base}{n}", n + 1
    try:
        lv = int(body.get("level") or cfg.get("level", 1) or 1)
    except (TypeError, ValueError):
        return _bad("Level must be a number from 1 to 5.")
    if not 1 <= lv <= len(LEVELS):
        return _bad(f"Level must be between 1 and {len(LEVELS)}.")
    people = []
    for a in body.get("assignees") or []:
        nm = str((a or {}).get("name") or "").strip()[:80]
        em = str((a or {}).get("email") or "").strip().lower()[:120]
        if nm or em:
            if em and "@" not in em:
                return _bad(f"'{em}' is not an email.")
            people.append({"name": nm or em, "email": em, "project": pid, "owner": False})
    rec = {"id": pid, "name": name, "short": str(body.get("short") or name)[:24], "domain": domain,
           "level": lv, "active": True, "pages": ["/"],
           "niche": str(body.get("niche") or "").strip()[:400], "keywords": []}
    cfg["projects"] = [x for x in cfg.get("projects") or [] if isinstance(x, dict)] + [rec]
    cfg["roster"] = (cfg.get("roster") or DEFAULT_CONFIG["roster"]) + people
    store.put_config(cfg, user.get("name", "superuser"))
    audit.stamp_user(user, "project.add", target=pid,
                     detail={"domain": domain, "level": lv, "assigned": [p["email"] or p["name"] for p in people]})
    return 201, {"project": projects_of(cfg)[pid], "config": cfg}


# --------------------------------------------------------------- config
def get_config(user):
    if not user:
        return ERR_AUTH
    return 200, store.get_config()


def put_config(user, body):
    guard = _super(user)
    if guard:
        return guard
    body = body or {}
    cfg = store.get_config()
    if "level" in body:
        try:
            lv = int(body["level"])
        except (TypeError, ValueError):
            return _bad("Level must be a number from 1 to 5.")
        if not 1 <= lv <= len(LEVELS):
            return _bad(f"Level must be between 1 and {len(LEVELS)}.")
        cfg["level"] = lv
    if "roster" in body:
        roster = body["roster"]
        if not isinstance(roster, list) or not roster:
            return _bad("The team needs at least one person.")
        # v1.3: optional email binds the row to a login exactly (assignments.py).
        clean = [{"name": str(m.get("name") or "").strip(),
                  "email": str(m.get("email") or "").strip().lower(),
                  "project": _project(m.get("project")), "owner": bool(m.get("owner"))}
                 for m in roster if str(m.get("name") or "").strip()]
        if not any(m["owner"] for m in clean):
            return _bad("At least one person must stay superuser.")
        cfg["roster"] = clean
    if "levels" in body:
        # {"1": {"target": 300, "min_links": 40}, ...} — only editable fields, bounded.
        raw = body["levels"]
        if not isinstance(raw, dict):
            return _bad("Levels must be an object keyed by level number.")
        clean_levels = {}
        for n, fields in raw.items():
            if str(n) not in {str(L["n"]) for L in LEVELS} or not isinstance(fields, dict):
                return _bad(f"Unknown level {n!r}.")
            keep = {}
            for k, (lo, hi) in LEVEL_EDITABLE.items():
                if k in fields and fields[k] not in (None, ""):
                    try:
                        keep[k] = max(lo, min(hi, int(fields[k])))
                    except (TypeError, ValueError):
                        return _bad(f"Level {n}: {k} must be a whole number.")
            if keep:
                clean_levels[str(n)] = keep
        cfg["levels"] = clean_levels
    if "projects" in body:
        # A list of sites. Seed sites can be edited (name, pages, active…) but
        # not removed; new ones need at least an id, a name and a domain.
        raw = body["projects"]
        if not isinstance(raw, list):
            return _bad("Projects must be a list.")
        clean_projects = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "").strip().lower()
            pid = "".join(ch for ch in pid if ch.isalnum() or ch in "-_")[:32]
            if not pid:
                return _bad("Every site needs a short id (letters and numbers).")
            rec = {"id": pid}
            for k in ("name", "short", "domain", "hue", "initial", "niche"):
                if p.get(k) not in (None, ""):
                    rec[k] = str(p[k]).strip()[:400 if k == "niche" else 80]
            if "domain" in rec:
                rec["domain"] = rec["domain"].lower().replace("https://", "").replace("http://", "").strip("/")
                if "." not in rec["domain"] or " " in rec["domain"]:
                    return _bad(f"'{rec['domain']}' does not look like a domain.")
            if "pages" in p:
                pages = p["pages"] if isinstance(p["pages"], list) else str(p["pages"]).split(",")
                rec["pages"] = [("/" + str(x).strip().lstrip("/")) for x in pages if str(x).strip()][:60] or ["/"]
            if "keywords" in p:
                kws = p["keywords"] if isinstance(p["keywords"], list) else str(p["keywords"]).splitlines()
                rec["keywords"] = [str(x).strip() for x in kws if str(x).strip()][:200]
            if "active" in p:
                rec["active"] = bool(p["active"])
            # v1.4: a site's own level. Not sent = keep what it had.
            if p.get("level") not in (None, ""):
                try:
                    lv = int(p["level"])
                except (TypeError, ValueError):
                    return _bad(f"{pid}: level must be 1 to {len(LEVELS)}.")
                if not 1 <= lv <= len(LEVELS):
                    return _bad(f"{pid}: level must be 1 to {len(LEVELS)}.")
                rec["level"] = lv
            else:
                old = next((x for x in cfg.get("projects") or [] if isinstance(x, dict) and x.get("id") == pid), {})
                if old.get("level"):
                    rec["level"] = old["level"]
            if pid not in projects_of() and not (rec.get("name") and rec.get("domain")):
                return _bad(f"New site '{pid}' needs a name and a domain.")
            clean_projects.append(rec)
        cfg["projects"] = clean_projects
    store.put_config(cfg, user.get("name", "superuser"))
    audit.stamp_user(user, "config.update",
                     detail={"level": cfg.get("level"),
                             "roster_size": len(cfg.get("roster", [])),
                             "level_overrides": sorted((cfg.get("levels") or {}).keys()),
                             "projects": [p["id"] for p in cfg.get("projects") or []]})
    return 200, cfg


# --------------------------------------------------------------- auto-review
def auto_review_run(user):
    """Superuser's "Run now". The cron path calls autoreview.run() directly
    from the adapter after checking the shared secret."""
    guard = _super(user)
    if guard:
        return guard
    from . import autoreview
    summary = autoreview.run(trigger="manual", actor=user.get("name", "superuser"))
    return 200, {"run": summary}


def auto_review_status(user):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    return 200, {"last": store.get_meta("autoreview_last"),
                 "enabled": settings.AUTOREVIEW, "ai": ai.available(),
                 "pending": len(store.pending_entries(settings.AUTOREVIEW_MAX_AGE_DAYS))}


# --------------------------------------------------------------- admin tools
def audit_trail(user, limit=200):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    try:
        n = min(max(int(limit), 1), 1000)
    except (TypeError, ValueError):
        n = 200
    return 200, {"events": audit.recent(n)}


def ai_selftest(user):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    res = ai.selftest()
    audit.stamp_user(user, "ai.selftest", target=res.get("provider"),
                     detail={"ok": res.get("ok"), "model": res.get("model")})
    return (200 if res.get("ok") else 502), res


def make_backup(user):
    if not user:
        return ERR_AUTH
    if not is_superuser(user):
        return ERR_FORBID
    path = store.backup("manual")
    pruned = store.prune_backups()
    audit.stamp_user(user, "backup.manual", target=path, detail={"pruned": pruned})
    return 200, {"path": path, "pruned": pruned}


# --------------------------------------------------------------- the page
def page_html():
    """The desk page. Read from disk each call in debug, cached otherwise.
    No template engine: four placeholders, one string replace each — so the
    module adds no Jinja dependency to a FastAPI host."""
    import os
    global _PAGE_CACHE
    path = os.path.join(os.path.dirname(__file__), "templates", "backlink_ops", "index.html")
    html = _PAGE_CACHE
    if html is None:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        _PAGE_CACHE = html
    return (html.replace("__BO_API__", json.dumps(settings.API_PREFIX))
                .replace("__BO_VERSION__", json.dumps(settings.VERSION))
                .replace("__BO_TOKEN_KEY__", json.dumps(settings.TOKEN_STORAGE_KEY))
                .replace("__BO_LOGIN_URL__", json.dumps(settings.LOGIN_URL)))


_PAGE_CACHE = None
