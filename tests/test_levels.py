"""Backlink Ops v1.3 — assignments (T1) and per-person, per-site levels (T2).

  * a rostered person sees their site even when it is marked not live, and is
    matched by login email or by name ignoring case and spaces
  * someone not on that site still does not see a hidden site
  * levels: two people on one site, and one person on two sites, each carry
    their own level; a person's score is their own links only
  * upgrade from schema 1 keeps the old global level for everyone
  * streak counts clean days back from yesterday; five in a row = ready
  * flag off: no "mine", /levels answers 404, everything else as before

Run:  PYTHONPATH=api python tests/test_levels.py
"""
import importlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# The user hook imports this file a second time as tests.test_levels; keep one temp dir.
TMP = os.environ.setdefault("BO_LEVELS_TMP", tempfile.mkdtemp(prefix="bo-levels-"))
os.environ.update({
    "BACKLINK_OPS_ENABLED": "1", "BACKLINK_OPS_AI_PROVIDER": "none",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"),
    "BACKLINK_OPS_BACKUP_DIR": os.path.join(TMP, "bk"),
    "BACKLINK_OPS_USER_HOOK": "tests.test_levels:hook",
    "BACKLINK_OPS_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_ADMIN_ROLES": "admin,seo_lead,seo,owner",
    "BACKLINK_OPS_VIEWER_ROLES": "viewer",
})

USERS = {
    "jai":   {"id": 1, "full_name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
    "akash": {"id": 7, "full_name": "Akash Yadav", "email": "akash0710yadav@gmail.com", "role": "seo_lead"},
    "a1":    {"id": 2, "full_name": "SEO Associate 1", "email": "seo1@agenticai.co", "role": "seo_lead"},
    "a2":    {"id": 3, "full_name": "SEO Associate 2", "email": "seo2@agenticai.co", "role": "seo_lead"},
}


def hook(request):
    u = USERS.get(request.headers.get("x-user"))
    return u and {"id": u["id"], "name": u["full_name"], "email": u["email"], "role": u["role"]}


PASS = 0


def check(label, cond):
    global PASS
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASS += 1


def fresh(flag):
    os.environ["FEATURE_PER_PROJECT_LEVELS"] = "1" if flag else "0"
    for name in [m for m in list(sys.modules) if m.startswith("app.backlink_ops")]:
        del sys.modules[name]
    bo = importlib.import_module("app.backlink_ops")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert bo.register(app)
    store = importlib.import_module("app.backlink_ops.store")
    return TestClient(app), store


API = "/api/seo/backlink-ops"


def as_(who):
    return {"x-user": who}


def link(c, who, project, url, da=45):
    r = c.post(API + "/entries", headers=as_(who), json={
        "project": project, "url": url, "type": "guest_post", "da": da, "spam": 1,
        "follow": "dofollow", "target": "/", "anchor": "read more", "kw": "x"})
    assert r.status_code == 201, r.text
    return r.json()


def main():
    # ------------------------------------------------ schema 1 database first
    c, store = fresh(False)
    conn = store.connect()
    with conn:   # pretend this is the live v1.2 file: global level 3, no level table yet
        conn.execute("DROP TABLE bo_user_levels")
        conn.execute("DELETE FROM bo_schema_version WHERE version > 1")
        conn.execute("INSERT OR IGNORE INTO bo_schema_version(version, applied_at, note) "
                     "VALUES (1, '2026-09-14', 'initial install')")
    r = c.put(API + "/config", headers=as_("jai"), json={
        "level": 3,
        "projects": [{"id": "whatsappauto", "active": False}],   # hidden, as on the live desk
        "roster": [
            {"name": "Jai", "project": "agenticai", "owner": True},
            {"name": "akash", "email": " AKASH0710yadav@gmail.com ", "project": "whatsappauto"},
            {"name": "seo associate 1", "project": "diymart"},      # name only, wrong case
            {"name": "SEO Associate 1", "project": "lettstart"},    # same person, second site
            {"name": "SEO Associate 2", "project": "diymart"},
        ]})
    check("superuser saves roster with an email column", r.status_code == 200
          and r.json()["roster"][1]["email"] == "akash0710yadav@gmail.com")

    print("\n--- T1: assignment and visibility ---")
    b = c.get(API + "/bootstrap", headers=as_("akash")).json()
    check("Akash is matched by email despite case/spaces", b["assigned"] == ["whatsappauto"])
    check("Akash lands on his site", b["project"] == "whatsappauto")
    check("a hidden site stays visible to the person rostered on it", "whatsappauto" in b["visible"])
    b2 = c.get(API + "/bootstrap", headers=as_("a2")).json()
    check("...and stays hidden from someone not on it", "whatsappauto" not in b2["visible"])
    b1 = c.get(API + "/bootstrap", headers=as_("a1")).json()
    check("name match ignores case; two rows = two sites", b1["assigned"] == ["diymart", "lettstart"])
    bj = c.get(API + "/bootstrap", headers=as_("jai")).json()
    check("superuser sees every site", set(bj["visible"]) >= {"whatsappauto", "diymart", "lettstart"})
    check("flag off: bootstrap says so", bj["perProjectLevels"] is False)
    d = c.get(API + "/day?project=diymart", headers=as_("a1")).json()
    check("flag off: no per-person scorecard", "mine" not in d)
    check("flag off: /levels answers 404", c.get(API + "/levels", headers=as_("a1")).status_code == 404)

    # ------------------------------------------------ restart with the flag on
    print("\n--- T2: per-person, per-site levels ---")
    c, store = fresh(True)
    mig = store.get_meta("levels_v2_migration")
    check("upgrade to schema 2 recorded the global level (3)", mig and mig["global_level"] == 3)
    check("schema version is now 2", store.schema_version() == 2)

    link(c, "a1", "diymart", "https://one.example/a")
    link(c, "a1", "diymart", "https://two.example/a")
    day2 = link(c, "a2", "diymart", "https://three.example/a")
    check("site view still adds up everyone's links", day2["counted"] == 3)
    check("a2's own scorecard counts only a2's link", day2["mine"]["counted"] == 1)
    d1 = c.get(API + "/day?project=diymart", headers=as_("a1")).json()
    check("a1's own scorecard counts only a1's links", d1["mine"]["counted"] == 2)
    check("a1 + a2 points = site points",
          round(d1["mine"]["points"] + day2["mine"]["points"], 1) == d1["points"])
    check("new pairs start at the old global level (nobody drops)", d1["mine"]["level"]["n"] == 3)

    g = c.get(API + "/levels/all", headers=as_("jai")).json()
    pairs = {(r["userId"], r["project"]) for r in g["rows"]}
    check("grid has both people on DIYMart", {("2", "diymart"), ("3", "diymart")} <= pairs)
    check("Akash shows as an unmatched roster row until he opens the desk",
          any(u["email"] == "akash0710yadav@gmail.com" for u in g["unmatched"]))
    check("only the superuser reads the grid",
          c.get(API + "/levels/all", headers=as_("a1")).status_code == 403)

    r = c.put(API + "/levels", headers=as_("jai"), json={"userId": "2", "project": "diymart", "level": 5})
    check("superuser raises a1 on DIYMart to L5", r.status_code == 200 and r.json()["level"] == 5)
    check("an associate cannot set levels",
          c.put(API + "/levels", headers=as_("a1"),
                json={"userId": "2", "project": "diymart", "level": 1}).status_code == 403)
    t1 = c.get(API + "/day?project=diymart", headers=as_("a1")).json()["mine"]
    t2 = c.get(API + "/day?project=diymart", headers=as_("a2")).json()["mine"]
    check("two people on one site now have different levels",
          t1["level"]["n"] == 5 and t2["level"]["n"] == 3 and t1["target"] != t2["target"])
    t1b = c.get(API + "/day?project=lettstart", headers=as_("a1")).json()["mine"]
    check("one person on two sites has two levels", t1b["level"]["n"] == 3)

    mine = c.get(API + "/levels", headers=as_("a1")).json()
    check("My Levels lists a1's two sites", [r["project"] for r in mine["rows"]] == ["diymart", "lettstart"])

    bk = c.get(API + "/bootstrap", headers=as_("akash")).json()
    check("Akash still lands on WA Auto with the flag on", bk["project"] == "whatsappauto")
    ak = c.get(API + "/levels", headers=as_("akash")).json()["rows"]
    check("Akash's My Levels shows whatsappautomation.co.in",
          ak and ak[0]["domain"] == "whatsappautomation.co.in")

    print("\n--- streak ---")
    c.put(API + "/config", headers=as_("jai"), json={"levels": {
        "3": {"target": 10, "min_links": 1, "queries": 0, "min_avg_da": 0, "high_value": 0}}})
    today = date.fromisoformat(store.today_ist())
    for back in (1, 2, 3, 4, 5):
        d = (today - timedelta(days=back)).isoformat()
        store.add_entry({"id": f"old{back}", "project": "diymart", "date": d, "author": "SEO Associate 2",
                         "url": f"https://old{back}.example/x", "host": f"old{back}.example",
                         "type": "guest_post", "da": 45, "spam": 0, "follow": "dofollow",
                         "target": "/", "anchor": "read more", "kw": "x", "relevant": 1,
                         "indexed": 1, "created_at": d + "T05:00:00+00:00"})
    a2 = {r["project"]: r for r in c.get(API + "/levels", headers=as_("a2")).json()["rows"]}["diymart"]
    check("five clean days in a row = 5-day streak", a2["streak"] == 5)
    check("...and the pair shows ready for the next level", a2["ready"] is True)
    check("XP is lifetime points on that site", a2["xp"] > a2["todayPoints"] > 0)
    store.set_decision("old3", "rejected", "spam", "Jai")
    a2 = {r["project"]: r for r in c.get(API + "/levels", headers=as_("a2")).json()["rows"]}["diymart"]
    check("a rejected link breaks that day, so the streak restarts", a2["streak"] == 2)

    b = c.get(API + "/board?days=14", headers=as_("jai")).json()
    lv = {(s["author"], s["project"]): s["level"] for s in b["series"]}
    check("scoreboard judges each pair at its own level",
          lv.get(("SEO Associate 1", "diymart")) == 5 and lv.get(("SEO Associate 2", "diymart")) == 3)

    print(f"\nAll {PASS} level checks passed.")


if __name__ == "__main__":
    main()
