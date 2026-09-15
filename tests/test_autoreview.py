"""Backlink Ops — auto-review (v1.1) tests. No network: the verifier's HTML
inspection is exercised on inline pages, and the run loop on a temporary
SQLite file with `fetch` monkeypatched.

Run:  python -m pytest tests/test_autoreview.py -q
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("BACKLINK_OPS_DB", os.path.join(tempfile.mkdtemp(), "bo-test.db"))
os.environ["BACKLINK_OPS_AI_PROVIDER"] = "none"

from app.backlink_ops import autoreview, seed, store  # noqa: E402
from app.backlink_ops import service  # noqa: E402

AG = seed.PROJECTS["agenticai"]


def _fresh():
    """Same file, same thread-cached connection — just empty the tables."""
    store.init_db()
    conn = store.connect()
    with conn:
        for t in ("bo_entries", "bo_reviews", "bo_queries", "bo_bank", "bo_coach", "bo_config", "bo_audit", "bo_ai_usage"):
            conn.execute(f"DELETE FROM {t}")


# --------------------------------------------------------------- inspect()
def test_inspect_finds_our_link_and_reads_rel():
    html = ('<html><head><title> Best  tools </title></head><body>'
            '<a href="https://other.com/x">nope</a>'
            '<a href="https://www.agenticaiautomation.co/whatsapp-automation" rel="nofollow ugc">'
            'WhatsApp automation</a></body></html>')
    r = autoreview.inspect(html, "agenticaiautomation.co", "whatsapp automation")
    assert r["found"] is True and r["follow"] == "nofollow"
    assert r["anchor_match"] is True and r["title"] == "best tools" and r["matches"] == 1


def test_inspect_prefers_the_anchor_that_matches():
    html = ('<a href="https://agenticaiautomation.co/" rel="nofollow">home</a>'
            '<a href="https://agenticaiautomation.co/ai-agents">ai agents for clinics</a>')
    r = autoreview.inspect(html, "agenticaiautomation.co", "AI agents")
    assert r["found"] and r["follow"] == "dofollow" and r["anchor_match"] is True


def test_inspect_ignores_lookalike_domains():
    html = '<a href="https://agenticaiautomation.co.evil.com/">x</a><a href="/local">y</a>'
    r = autoreview.inspect(html, "agenticaiautomation.co", "x")
    assert r["found"] is False and r["matches"] == 0


def test_inspect_survives_broken_html():
    r = autoreview.inspect("<a href='https://diymart.in/store'>store<div><a", "diymart.in", "store")
    assert r["found"] is True


# --------------------------------------------------------------- seed helpers
def test_projects_merge_runtime_overrides_and_new_sites():
    cfg = {"projects": [
        {"id": "whatsappauto", "active": True, "pages": ["/pricing", "/clinics"]},
        {"id": "newsite", "name": "New.in", "domain": "new.in", "short": "New"},
    ]}
    P = seed.projects(cfg)
    assert P["whatsappauto"]["active"] is True and P["whatsappauto"]["pages"] == ["/pricing", "/clinics"]
    assert P["whatsappauto"]["domain"] == "whatsappautomation.co.in"      # seed field kept
    assert P["newsite"]["name"] == "New.in" and P["newsite"]["pages"] == ["/"]
    assert set(seed.PROJECTS) <= set(P)                                    # seed sites never vanish
    assert seed.projects()["whatsappauto"]["active"] is False              # ships hidden


def test_level_override_is_bounded():
    assert seed.level(1)["min_links"] == 40
    L = seed.level(1, {"levels": {"1": {"target": 99999, "queries": "3"}}})
    assert L["target"] == 5000 and L["queries"] == 3


# --------------------------------------------------------------- run()
def _jai():
    return {"id": 1, "name": "Jai", "email": "contact@agenticaiautomation.co", "role": "superuser"}


def _assoc():
    return {"id": 2, "name": "Associate", "email": "a@x.co", "role": "admin"}


def _log(url, **kw):
    body = {"project": "agenticai", "url": url, "type": "directory", "da": 25, "spam": 1,
            "follow": "dofollow", "target": "/ai-agents", "anchor": "ai agents", "relevant": 1}
    body.update(kw)
    code, st = service.add_entry(_assoc(), body)
    assert code == 201, st
    return st["rows"][-1]["id"]


def test_run_applies_rules_without_network(monkeypatch):
    _fresh()
    pages = {
        "https://good.example/p":   (200, '<a href="https://agenticaiautomation.co/ai-agents">ai agents</a>', None),
        "https://nolink.example/p": (200, '<a href="https://elsewhere.com/">x</a>', None),
        "https://gone.example/p":   (404, None, "HTTP 404"),
        "https://wall.example/p":   (403, None, "HTTP 403"),
        "https://nf.example/p":     (200, '<a rel="nofollow" href="https://agenticaiautomation.co/">ai agents</a>', None),
    }
    monkeypatch.setattr(autoreview, "fetch", lambda url, timeout=None: pages.get(url, (0, None, "dns")))
    monkeypatch.setattr(autoreview.settings, "VERIFY_MIN_GAP", 0)

    ids = {k: _log(k) for k in pages}
    ids["spam"] = _log("https://spammy.example/p", spam=9)

    summary = autoreview.run(trigger="test")
    assert summary["checked"] == 6
    assert summary["ai"] == "off"

    dec = store.decisions_for("agenticai", store.today_ist())
    assert dec[ids["https://good.example/p"]]["status"] == "approved"
    assert dec[ids["https://nolink.example/p"]]["status"] == "needs_fix"
    assert "not on that page" in dec[ids["https://nolink.example/p"]]["note"]
    assert dec[ids["https://gone.example/p"]]["status"] == "needs_fix"
    assert dec[ids["https://wall.example/p"]]["status"] == "pending"     # human look, not a bounce
    assert dec[ids["spam"]]["status"] == "needs_fix"
    # The page said nofollow although the form said dofollow: corrected, still approved.
    nf = dec[ids["https://nf.example/p"]]
    assert nf["status"] == "approved" and "corrected to nofollow" in nf["note"]
    row = next(e for e in store.entries_for("agenticai", store.today_ist()) if e["id"] == ids["https://nf.example/p"])
    assert row["follow"] == "nofollow"

    assert summary["approved"] == 2 and summary["sent_back"] == 3 and summary["flagged"] == 1
    assert store.get_meta("autoreview_last")["checked"] == 6
    # A second run finds only the flagged one still pending.
    assert len(store.pending_entries()) == 1


def test_run_uses_ai_verdicts_when_available(monkeypatch):
    _fresh()
    monkeypatch.setattr(autoreview, "fetch",
                        lambda url, timeout=None: (200, '<a href="https://agenticaiautomation.co/">ai agents</a>', None))
    monkeypatch.setattr(autoreview.settings, "VERIFY_MIN_GAP", 0)
    monkeypatch.setattr(autoreview.ai, "available", lambda: True)
    a, b = _log("https://one.example/p"), _log("https://two.example/p", da=95)

    def fake_batch(groups):
        links = [l for g in groups for l in g["links"]]
        assert all(l["link_found"] is True for l in links)
        return {a: {"verdict": "approve", "note": ""},
                b: {"verdict": "needs_fix", "note": "DA 95 is not plausible for this blog — enter the real DA."}}
    monkeypatch.setattr(autoreview.ai, "review_batch", fake_batch)
    monkeypatch.setattr(autoreview.settings, "AI_PROVIDER", "grok")

    s = autoreview.run(trigger="test")
    assert s["ai"] == "grok" and s["approved"] == 1 and s["sent_back"] == 1
    dec = store.decisions_for("agenticai", store.today_ist())
    assert dec[a]["status"] == "approved" and dec[a]["by"] == "ai"
    assert dec[b]["status"] == "needs_fix" and "plausible" in dec[b]["note"]


def test_put_config_validates_levels_and_projects():
    _fresh()
    code, out = service.put_config(_jai(), {"levels": {"1": {"target": 300, "min_links": 35}}})
    assert code == 200 and out["levels"]["1"] == {"target": 300, "min_links": 35}
    code, out = service.put_config(_jai(), {"levels": {"9": {"target": 1}}})
    assert code == 400
    code, out = service.put_config(_jai(), {"projects": [{"id": "x y", "name": "X", "domain": "x.in"}]})
    assert code == 200 and out["projects"][0]["id"] == "xy"
    code, out = service.put_config(_jai(), {"projects": [{"id": "new", "name": "N"}]})
    assert code == 400 and "domain" in out["message"]
    code, out = service.put_config(_jai(), {"projects": [{"id": "whatsappauto", "active": True,
                                                          "pages": "/pricing, clinics"}]})
    assert code == 200
    code, boot = service.bootstrap(_assoc())
    assert boot["projects"]["whatsappauto"]["active"] is True
    assert boot["projects"]["whatsappauto"]["pages"] == ["/pricing", "/clinics"]
    # Associates cannot touch config at all.
    assert service.put_config(_assoc(), {"levels": {}})[0] == 403
    assert service.auto_review_run(_assoc())[0] == 403
