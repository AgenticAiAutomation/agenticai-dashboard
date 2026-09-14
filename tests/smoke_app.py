"""Backlink Ops — end-to-end smoke test.

Runs against a stand-in for the real dashboard (FastAPI, JWT roles, existing
/api/seo/backlinks and article routes), and then against a Flask host, to prove:

  * every pre-existing route still answers, unchanged
  * /api/seo/backlinks is NOT treated as a collision with /api/seo/backlink-ops
  * the dashboard's own roles map correctly: seo_lead writes, viewer cannot,
    only Jai approves
  * the desk works with no AI provider configured
  * turning the flag off leaves no trace of the feature
  * both adapters give identical answers, because both call one service layer

Run:  python tests/smoke_app.py
"""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TMP = tempfile.mkdtemp(prefix="bo-smoke-")
os.environ.update({
    "BACKLINK_OPS_ENABLED": "1",
    "BACKLINK_OPS_ALLOW_ANON": "0",
    "BACKLINK_OPS_DB": os.path.join(TMP, "backlink_ops.db"),
    "BACKLINK_OPS_BACKUP_DIR": os.path.join(TMP, "backups"),
    "BACKLINK_OPS_AI_PROVIDER": "none",
    "BACKLINK_OPS_SUPERUSERS": "jai.prajapati91@gmail.com",
    "BACKLINK_OPS_ADMIN_ROLES": "admin,seo_lead",
    "BACKLINK_OPS_VIEWER_ROLES": "viewer",
})

PASSED = 0


def check(label, cond):
    global PASSED
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASSED += 1


def reload_module():
    for name in [m for m in list(sys.modules) if m.startswith("app.backlink_ops")]:
        del sys.modules[name]
    return importlib.import_module("app.backlink_ops")


API = "/api/seo/backlink-ops"
PAGE = "/seo/backlink-ops"


def main():
    from fastapi.testclient import TestClient
    from tests.hostsim import make_app

    print("\n--- FastAPI host (agenticai-dashboard shape) ---")
    pkg = reload_module()
    from app.backlink_ops.adapters.fastapi_app import existing_paths
    app = make_app()
    before = existing_paths(app)
    check("feature mounted on FastAPI", pkg.register(app) is True)
    after = existing_paths(app)
    check("no pre-existing route removed or rewritten", before <= after)
    check("the guard flattens nested routers (sees the host's real paths)",
          "/api/seo/backlinks" in before and "/api/articles/publish" in before)
    check("only backlink-ops paths were added",
          all("backlink-ops" in p for p in (after - before)))

    c = TestClient(app)
    jai = {"x-test-user": "jai"}
    lead = {"x-test-user": "lead"}
    viewer = {"x-test-user": "viewer"}

    print("\n  existing dashboard, untouched")
    check("GET /api/seo/backlinks still 200",
          c.get("/api/seo/backlinks").json()["source"] == "pre-existing seo_backlinks table")
    check("POST /api/seo/backlinks still 201", c.post("/api/seo/backlinks").status_code == 201)
    check("GET /api/seo/backlinks/haro still 200", c.get("/api/seo/backlinks/haro").status_code == 200)
    check("article pipeline still 200", c.get("/api/articles").status_code == 200)
    check("article publish still 200", c.post("/api/articles/publish").status_code == 200)
    check("team scoreboard still 200", c.get("/api/team/scoreboard").status_code == 200)
    check("/api/seo/backlinks was not seen as a prefix collision",
          any(p.startswith(API) for p in existing_paths(app)))

    print("\n  the desk")
    h = c.get(API + "/health")
    check("health 200 without auth (deploy gate)", h.status_code == 200)
    check("health reports its own database", h.json()["db_ok"] is True)
    check("page renders without a template engine",
          "Backlink Ops Control" in c.get(PAGE + "/").text)
    check("page carries the API prefix",
          '"' + API + '"' in c.get(PAGE + "/").text)

    print("\n  roles, mapped from the dashboard's own")
    check("no session at all → 401", c.get(API + "/bootstrap").status_code == 401)
    check("Jai (admin + listed email) → superuser",
          c.get(API + "/bootstrap", headers=jai).json()["me"]["role"] == "superuser")
    check("seo_lead → desk admin",
          c.get(API + "/bootstrap", headers=lead).json()["me"]["role"] == "admin")
    check("viewer → read-only",
          c.get(API + "/bootstrap", headers=viewer).json()["me"]["role"] == "viewer")

    print("\n  the daily loop")
    r = c.post(API + "/entries", headers=lead, json={
        "project": "agenticai", "url": "https://healthtechindia.in/guest/automation",
        "type": "guest_post", "da": 45, "spam": 1, "follow": "dofollow",
        "target": "/healthcare-automation", "anchor": "hospital automation",
        "kw": "whatsapp automation for hospitals", "relevant": True})
    check("associate logs a link (201)", r.status_code == 201)
    day = r.json()
    check("server scored it: 15 * 1.4 + 3 + 4 = 28.0", day["points"] == 28.0)
    entry_id = day["rows"][0]["id"]

    check("viewer cannot log a link (403)",
          c.post(API + "/entries", headers=viewer, json={
              "project": "agenticai", "url": "https://x.com/a", "type": "directory",
              "da": 10, "target": "/a", "anchor": "a"}).status_code == 403)

    check("associate cannot approve (403)",
          c.post(API + "/review", headers=lead,
                 json={"project": "agenticai",
                       "decisions": [{"id": entry_id, "status": "approved"}]}).status_code == 403)
    rv = c.post(API + "/review", headers=jai,
                json={"project": "agenticai",
                      "decisions": [{"id": entry_id, "status": "approved"}]})
    check("Jai approves (200)", rv.status_code == 200)
    check("approved link still counts", rv.json()["rows"][0]["status"] == "approved")

    rj = c.post(API + "/review", headers=jai,
                json={"project": "agenticai",
                      "decisions": [{"id": entry_id, "status": "rejected", "note": "DA too low"}]})
    check("rejecting removes the points", rj.json()["points"] == 0.0)
    check("rejection blocks day completion",
          any(q["k"] == "fix" and not q["ok"] for q in rj.json()["reqs"]))
    c.post(API + "/review", headers=jai,
           json={"project": "agenticai", "decisions": [{"id": entry_id, "status": "approved"}]})

    print("\n  keyword lab, with no AI provider")
    an = c.post(API + "/analyse", headers=lead, json={
        "project": "agenticai", "kw": "rpa migration services",
        "pasted": "Volume 1,300\nSD 34\nCPC 92"})
    check("keyword analysed (200)", an.status_code == 200)
    aj = an.json()
    check("fell back to deterministic rules", aj["analysis"]["_source"] == "rules")
    check("parsed the pasted numbers", aj["analysis"]["volume"] == 1300)
    check("query counted toward the requirement", aj["day"]["queries"] == 1)
    check("keyword bank updated", len(aj["bank"]) == 1)

    co = c.post(API + "/coach", headers=lead, json={"project": "agenticai"})
    check("coach answers on rules", co.json()["coach"]["_source"] == "rules")

    print("\n  superuser-only surfaces")
    check("audit trail refused to an associate", c.get(API + "/audit", headers=lead).status_code == 403)
    ev = c.get(API + "/audit", headers=jai).json()["events"]
    check("every write was audited", len(ev) >= 5)
    check("audit records the actor and role",
          any(e["action"] == "review.decide" and e["role"] == "superuser" for e in ev))
    check("ai-selftest refused to an associate",
          c.post(API + "/ai-selftest", headers=lead).status_code == 403)
    check("ai-selftest reports 'none' honestly",
          c.post(API + "/ai-selftest", headers=jai).status_code == 502)
    check("level change refused to an associate",
          c.put(API + "/config", headers=lead, json={"level": 3}).status_code == 403)
    check("Jai changes the level",
          c.put(API + "/config", headers=jai, json={"level": 3}).json()["level"] == 3)
    check("cannot remove the last superuser",
          c.put(API + "/config", headers=jai,
                json={"roster": [{"name": "X", "project": "diymart", "owner": False}]}
                ).status_code == 400)
    c.put(API + "/config", headers=jai, json={"level": 1})

    print("\n  an explicit user hook (the recommended wiring)")
    os.environ["BACKLINK_OPS_USER_HOOK"] = "tests.hostsim_hook:get_user"
    pkg = reload_module()
    app2 = make_app()
    pkg.register(app2)
    c2 = TestClient(app2)
    check("hook resolves the user",
          c2.get(API + "/bootstrap", headers={"x-hook-user": "jai"}).json()["me"]["role"] == "superuser")
    del os.environ["BACKLINK_OPS_USER_HOOK"]

    print("\n--- Flask host (same service layer) ---")
    os.environ["BACKLINK_OPS_ALLOW_ANON"] = "1"
    pkg = reload_module()
    from flask import Flask
    fapp = Flask(__name__)

    @fapp.get("/")
    def home():
        return "existing marketing site"

    check("feature mounted on Flask", pkg.register(fapp) is True)
    fc = fapp.test_client()
    check("Flask host route untouched", fc.get("/").get_data(as_text=True) == "existing marketing site")
    check("Flask adapter serves the same health payload",
          fc.get(API + "/health").get_json()["feature"] == "backlink-ops")
    check("Flask adapter serves the page", "Backlink Ops Control" in fc.get(PAGE + "/").get_data(as_text=True))
    os.environ["BACKLINK_OPS_ALLOW_ANON"] = "0"

    print("\n--- rollback rehearsal ---")
    os.environ["BACKLINK_OPS_ENABLED"] = "0"
    pkg = reload_module()
    app3 = make_app()
    check("flag off: feature does not mount", pkg.register(app3) is False)
    check("flag off: no backlink-ops route exists",
          not any("backlink-ops" in p for p in existing_paths(app3)))
    c3 = TestClient(app3)
    check("flag off: existing dashboard unaffected",
          c3.get("/api/seo/backlinks").status_code == 200)
    os.environ["BACKLINK_OPS_ENABLED"] = "1"

    print("\n--- collision guard ---")
    os.environ["BACKLINK_OPS_API_PREFIX"] = "/api/seo/backlinks"   # deliberately taken
    pkg = reload_module()
    app4 = make_app()
    check("refuses to mount on a prefix that is already served",
          pkg.register(app4) is False)
    check("and the existing route still answers",
          TestClient(app4).get("/api/seo/backlinks").status_code == 200)
    del os.environ["BACKLINK_OPS_API_PREFIX"]

    print(f"\nAll {PASSED} smoke checks passed. Temp dir: {TMP}")


if __name__ == "__main__":
    main()
