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

from . import ai, audit, store
from .config import settings
from .identity import can_write, is_superuser
from .scoring import day_stats, host_of
from .seed import (DEFAULT_CONFIG, LEVELS, LINK_TYPES, PROJECTS, SEED_KEYWORDS,
                   TYPE_MAP, level as level_for)

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
    return p if p in PROJECTS else "agenticai"


def _stats(project, date):
    cfg = store.get_config()
    return day_stats(store.entries_for(project, date),
                     store.decisions_for(project, date),
                     store.queries_for(project, date),
                     cfg.get("level", 1), project, store.bank_keywords(project))


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
    return 200, {
        "me": user, "config": cfg, "levels": LEVELS,
        "level": level_for(cfg.get("level", 1)), "linkTypes": LINK_TYPES,
        "projects": PROJECTS, "seedKeywords": SEED_KEYWORDS,
        "today": store.today_ist(), "readOnly": settings.READ_ONLY or not can_write(user),
        "aiEnabled": ai.available(), "version": settings.VERSION,
        "project": _project(project),
    }


def day(user, project=None, date=None):
    if not user:
        return ERR_AUTH
    p, d = _project(project), (date or store.today_ist())
    st = _stats(p, d)
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
    return 201, _stats(project, e["date"])


def delete_entry(user, entry_id, project=None):
    guard = _writable(user)
    if guard:
        return guard
    p = _project(project)
    if not store.delete_entry(entry_id, p):
        return 404, {"error": "not_found", "message": "That link is no longer on the sheet."}
    audit.stamp_user(user, "entry.delete", target=entry_id, detail={"project": p})
    return 200, _stats(p, store.today_ist())


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
    return 200, {"analysis": out, "day": _stats(project, store.today_ist()),
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
    L = level_for(cfg.get("level", 1))
    series = [{"author": a, "project": p, "date": d, "points": v,
               "queries": queries.get((a, p, d), 0),
               "done": v >= L["target"] and queries.get((a, p, d), 0) >= L["queries"]}
              for (a, p, d), v in points.items()]
    return 200, {"series": series, "level": L,
                 "roster": cfg.get("roster", DEFAULT_CONFIG["roster"]),
                 "bankCounts": {p: len(store.bank_for(p)) for p in PROJECTS},
                 "days": days_back, "today": store.today_ist()}


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
        clean = [{"name": str(m.get("name") or "").strip(),
                  "project": _project(m.get("project")), "owner": bool(m.get("owner"))}
                 for m in roster if str(m.get("name") or "").strip()]
        if not any(m["owner"] for m in clean):
            return _bad("At least one person must stay superuser.")
        cfg["roster"] = clean
    store.put_config(cfg, user.get("name", "superuser"))
    audit.stamp_user(user, "config.update",
                     detail={"level": cfg.get("level"),
                             "roster_size": len(cfg.get("roster", []))})
    return 200, cfg


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
    No template engine: two placeholders, one string replace — so the module
    adds no Jinja dependency to a FastAPI host."""
    import os
    global _PAGE_CACHE
    path = os.path.join(os.path.dirname(__file__), "templates", "backlink_ops", "index.html")
    html = _PAGE_CACHE
    if html is None:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        _PAGE_CACHE = html
    return (html.replace("__BO_API__", json.dumps(settings.API_PREFIX))
                .replace("__BO_VERSION__", json.dumps(settings.VERSION)))


_PAGE_CACHE = None
