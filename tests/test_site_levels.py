"""Backlink Ops v1.4 — a difficulty level per website, and "add a project".

Reported 23 Oct 2026: setting L4 for one website showed L4 on every website.
  * setting a website's level changes that website only (per-site levels off AND on)
  * people on a site follow its level; Jai can still set one person's level by hand,
    and put them back to "follow the website"
  * "Save websites" keeps each site's level
  * add a project: website + who works on it + level, in one call; superuser only

Run:  PYTHONPATH="api;." python tests/test_site_levels.py
"""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
TMP = os.environ.setdefault("SL_TEST_TMP", tempfile.mkdtemp(prefix="sl-"))
os.environ.update({
    "BACKLINK_OPS_ENABLED": "1", "BACKLINK_OPS_AI_PROVIDER": "none",
    "BACKLINK_OPS_DB": os.path.join(TMP, "bo.db"), "BACKLINK_OPS_BACKUP_DIR": os.path.join(TMP, "bk"),
    "BACKLINK_OPS_USER_HOOK": "tests.test_site_levels:hook",
    "BACKLINK_OPS_SUPERUSERS": "contact@agenticaiautomation.co",
    "BACKLINK_OPS_ADMIN_ROLES": "admin,seo_lead,seo,owner",
})
USERS = {"jai": {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "owner"},
         "akash": {"id": 7, "name": "Akash Yadav", "email": "akash0710yadav@gmail.com", "role": "seo_lead"},
         "priya": {"id": 8, "name": "Priya Sharma", "email": "priya@example.com", "role": "seo_lead"}}


def hook(request):
    return USERS.get(request.headers.get("x-user"))


PASS = 0


def check(label, cond):
    global PASS
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASS += 1


H = lambda w: {"x-user": w}  # noqa: E731
API = "/api/seo/backlink-ops"


def client(flag):
    os.environ["FEATURE_PER_PROJECT_LEVELS"] = flag
    for m in [m for m in list(sys.modules) if m.startswith("app.backlink_ops")]:
        del sys.modules[m]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    assert importlib.import_module("app.backlink_ops").register(app)
    return TestClient(app)


def lv(c, who, project):
    d = c.get(f"{API}/day?project={project}", headers=H(who)).json()
    return (d.get("mine") or d)["level"]["n"]


def main():
    print("--- per-site levels switch OFF (as live today) ---")
    c = client("0")
    c.put(f"{API}/config", headers=H("jai"), json={"level": 1, "roster": [
        {"name": "Jai", "project": "agenticai", "owner": True},
        {"name": "Akash", "email": "akash0710yadav@gmail.com", "project": "whatsappauto"},
        {"name": "Priya Sharma", "project": "diymart"}]})
    r = c.put(f"{API}/site-level", headers=H("jai"), json={"project": "whatsappauto", "level": 4})
    check("Jai sets WA Auto to L4", r.status_code == 200 and r.json()["siteLevels"]["whatsappauto"] == 4)
    check("WA Auto is L4", lv(c, "akash", "whatsappauto") == 4)
    check("DIYMart stays L1 (the bug: it used to follow)", lv(c, "priya", "diymart") == 1)
    check("AgenticAI stays L1", lv(c, "jai", "agenticai") == 1)
    b = c.get(f"{API}/bootstrap?project=diymart", headers=H("priya")).json()
    check("bootstrap reports each site's level", b["siteLevels"]["whatsappauto"] == 4 and b["siteLevels"]["diymart"] == 1)
    check("the level chip on DIYMart says L1", b["level"]["n"] == 1)
    check("an associate can't change a site's level",
          c.put(f"{API}/site-level", headers=H("akash"), json={"project": "whatsappauto", "level": 1}).status_code == 403)
    cfg = c.get(f"{API}/config", headers=H("jai")).json()
    projects = [{"id": p, "name": p} for p in ("agenticai", "diymart", "whatsappauto", "lettstart")]
    c.put(f"{API}/config", headers=H("jai"), json={"projects": projects})
    check("'Save websites' keeps WA Auto at L4", lv(c, "akash", "whatsappauto") == 4)
    c.put(f"{API}/config", headers=H("jai"), json={"level": 2})
    check("changing the default level moves only sites without their own (DIYMart → L2)",
          lv(c, "priya", "diymart") == 2 and lv(c, "akash", "whatsappauto") == 4)
    e = c.post(f"{API}/entries", headers=H("akash"), json={"project": "whatsappauto", "url": "https://x.example/1",
               "type": "guest_post", "da": 40, "spam": 1, "follow": "dofollow", "target": "/", "anchor": "a", "kw": "k"})
    check("logging on WA Auto scores against L4's target", e.json()["level"]["n"] == 4)
    board = c.get(f"{API}/board?days=14", headers=H("jai")).json()["series"]
    check("scoreboard judges WA Auto at L4", all(s["level"] == 4 for s in board if s["project"] == "whatsappauto"))

    print("\n--- per-site levels switch ON ---")
    c = client("1")
    check("people follow their website's level", lv(c, "akash", "whatsappauto") == 4 and lv(c, "priya", "diymart") == 2)
    c.put(f"{API}/levels", headers=H("jai"), json={"userId": "8", "project": "diymart", "level": 5})
    check("Jai sets Priya to L5 on DIYMart by hand", lv(c, "priya", "diymart") == 5)
    c.put(f"{API}/site-level", headers=H("jai"), json={"project": "diymart", "level": 3})
    check("…and a later site change doesn't overwrite her own level", lv(c, "priya", "diymart") == 5)
    c.put(f"{API}/levels", headers=H("jai"), json={"userId": "8", "project": "diymart", "reset": True})
    check("'follow the website' puts her back on the site's L3", lv(c, "priya", "diymart") == 3)
    g = c.get(f"{API}/levels/all", headers=H("jai")).json()["rows"]
    pr = [r for r in g if r["userId"] == "8"][0]
    check("grid shows override off and the site level", pr["override"] is False and pr["siteLevel"] == 3)

    print("\n--- add a project ---")
    r = c.post(f"{API}/projects", headers=H("jai"), json={
        "name": "Hospital Cloud", "domain": "https://www.hospitalcloud.ai/", "level": 2,
        "assignees": [{"name": "Akash", "email": "akash0710yadav@gmail.com"}]})
    check("Jai adds a project with level + assignee", r.status_code == 201)
    pid = r.json()["project"]["id"]
    check("domain cleaned, id made from it", r.json()["project"]["domain"] == "hospitalcloud.ai" and pid == "hospitalcloud")
    b = c.get(f"{API}/bootstrap", headers=H("akash")).json()
    check("Akash is assigned to it straight away", pid in b["assigned"] and pid in b["visible"])
    check("it starts at the level chosen (L2)", lv(c, "akash", pid) == 2)
    check("same domain twice is refused", c.post(f"{API}/projects", headers=H("jai"), json={
        "name": "Dup", "domain": "hospitalcloud.ai"}).status_code == 400)
    check("associates can't add projects", c.post(f"{API}/projects", headers=H("akash"), json={
        "name": "X", "domain": "x.example"}).status_code == 403)
    print(f"\nAll {PASS} site-level checks passed.")


if __name__ == "__main__":
    main()
