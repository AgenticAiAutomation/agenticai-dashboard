"""Blog Playbook — API-side tests. No database and no network.

Run:  python -m pytest tests/test_blog_playbook.py -q
      (and node tests/playbook/compose.test.mts for the composer itself)

tests/playbook/sample.md is the composer's output for the sample article, so
these tests score and render exactly what the dashboard would save.

Covers BLOG_PLAYBOOK_DASHBOARD_CHANGES_5thOct2026.md §6: score parity (1),
flag off (4), the publish gate at 79/80 (6), plus the skim score, the publish
converter and the routes.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
os.environ.update({
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "JWT_SECRET_KEY": "x", "INITIAL_OWNER_EMAIL": "a@b.co",
    "INITIAL_OWNER_PASSWORD": "x", "CORS_ORIGINS": "http://localhost",
})

from app.config import settings  # noqa: E402
from app.seo import playbook  # noqa: E402
from app.seo.routes import articles  # noqa: E402
from app.seo.services import (claude, playbook_render, rankmath,  # noqa: E402
                              scoring, skim)

SAMPLE = (ROOT / "tests" / "playbook" / "sample.md").read_text(encoding="utf-8")
KEYWORD = "whatsapp automation for clinics"
LEGACY = """# WhatsApp Automation for Clinics: A Practical Guide

WhatsApp automation for clinics cuts the time your front desk spends on calls.
This guide walks through what to automate first and what it costs.

## Why clinics lose appointments

**1. Reminders are manual**
Receptionists call each patient the day before.

- Calls go unanswered
- Patients forget

| Item | Cost |
|---|---|
| Setup | 25000 |

> Patients reply to WhatsApp faster than to calls.

> A second quote straight after the first.

## What to automate first

Start with confirmations and reminders.

[FROM AUTHOR: 200 words on real production story about clinics]
"""


@pytest.fixture
def flag(monkeypatch, tmp_path):
    """flag(True) switches the Playbook on for everyone; default is off.

    The dashboard-granted access file points at an empty temp dir, so a real
    file on this machine can never leak into a test.
    """
    monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ACCESS_FILE",
                        str(tmp_path / "instance" / "blog_playbook_access.json"))
    playbook._access_cache.update(mtime=None, value=None)

    def set_flag(on: bool, users: str = ""):
        monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ENABLED", on)
        monkeypatch.setattr(settings, "BLOG_PLAYBOOK_USERS", users)
    set_flag(False)
    return set_flag


def house(md: str) -> dict:
    ctx = scoring.ScoringContext(
        markdown=md, lines=md.splitlines(), primary_keyword=KEYWORD,
        title="WhatsApp Automation for Clinics: Cut No-Shows in 14 Days",
        slug="whatsapp-automation-for-clinics",
        meta_title="WhatsApp Automation for Clinics",
        meta_description="How whatsapp automation for clinics cuts no-shows.",
        from_author_story="word " * 130, featured_image_alt="Clinic desk",
        faqs=[{"question": f"Q{i}?", "answer": "An answer " * 8,
               "source_url": "https://reddit.com/r/x"} for i in range(5)],
    )
    return scoring.score_article(ctx)


def rank_math(md: str) -> dict:
    return rankmath.score_article(rankmath.RankMathContext(
        markdown=md, primary_keyword=KEYWORD, title="WhatsApp Automation for Clinics",
        slug="whatsapp-automation-for-clinics",
        meta_description="How whatsapp automation for clinics cuts no-shows.",
        has_featured_image=True, featured_image_alt="Clinic desk"))


# ------------------------------------------------------------ §6.1 parity
@pytest.mark.parametrize("md", [SAMPLE, LEGACY], ids=["playbook", "legacy"])
def test_scores_identical_with_flag_on_and_off(flag, md):
    flag(False)
    off = (house(md), rank_math(md))
    flag(True)
    on = (house(md), rank_math(md))
    assert off == on


def test_scorer_does_not_know_about_the_playbook():
    for module in (scoring, rankmath):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "skim" not in source and "playbook" not in source.lower()
    assert scoring.PUBLISH_MIN_SCORE == 80
    assert (scoring.WORD_COUNT_MIN, scoring.WORD_COUNT_MAX) == (1200, 2500)


def test_house_scorer_reads_the_sample_cleanly():
    report = house(SAMPLE)
    params = {p["key"]: p for p in report["parameters"]}
    assert params["heading_hierarchy"]["points_earned"] == 3
    # Keyword in title, meta, H1 and the first 100 words.
    assert params["keyword_placement"]["points_earned"] == 8
    # strip_markdown leaves no markup in the words the scorer counts.
    ctx = scoring.ScoringContext(markdown=SAMPLE, lines=[], primary_keyword=KEYWORD)
    assert ">" not in ctx.body_text and "**" not in ctx.body_text


# ------------------------------------------------------------ skim
def test_skim_sample_scores_full_marks():
    report = skim.score(SAMPLE, KEYWORD)
    assert report["advisory"] is True
    assert report["note"] == "Advisory — does not block publish"
    failing = [c for c in report["checks"] if not c["passed"]]
    assert failing == [] and report["total_score"] == 100


def test_skim_legacy_post_scores_low_and_explains():
    report = skim.score(LEGACY, KEYWORD)
    checks = {c["key"]: c for c in report["checks"]}
    assert checks["tldr"]["points_earned"] == 0
    assert checks["real_example"]["points_earned"] == 0
    assert checks["cta"]["points_earned"] == 0
    assert checks["table"]["points_earned"] == 10
    assert report["total_score"] < 70


def test_skim_flags_the_real_example_placeholder():
    md = SAMPLE.replace("> **Real example:**", "[REAL EXAMPLE: client]\n\n> **Note:**")
    check = {c["key"]: c for c in skim.score(md, KEYWORD)["checks"]}["real_example"]
    assert check["points_earned"] == 0 and "placeholder" in check["detail"]


def test_skim_long_section_and_long_text_run():
    filler = " ".join(["Plain words without any break at all."] * 50)   # 350 words
    md = SAMPLE.replace("Start with the messages your front desk sends most.", filler)
    checks = {c["key"]: c for c in skim.score(md, KEYWORD)["checks"]}
    assert not checks["section_length"]["passed"]
    assert "Which messages" in checks["section_length"]["detail"]
    assert not checks["visual_rhythm"]["passed"]


def test_skim_tldr_partial_credit():
    md = SAMPLE.replace("> - WhatsApp automation for clinics sends", "> - It sends")
    check = {c["key"]: c for c in skim.score(md, KEYWORD)["checks"]}["tldr"]
    assert check["points_earned"] == 14 and "first bullet" in check["detail"]


# ------------------------------------------------------------ publish HTML
def test_playbook_render_keeps_tables_and_separate_quotes():
    html = playbook_render.to_html(SAMPLE)
    assert html.count("<table>") == 2 and "<p>|" not in html
    # TL;DR, Who, Flow, Tip, Watch out, Pro tip, Real example, Next step.
    assert html.count("<blockquote>") == 8
    assert "<blockquote>\n<p><strong>TL;DR</strong></p>\n<ul>" in html
    assert "<p><strong>Who this is for:</strong>" in html


def test_playbook_render_drops_a_leftover_author_placeholder():
    assert "[FROM AUTHOR" in SAMPLE
    assert "FROM AUTHOR" not in playbook_render.to_html(SAMPLE)
    # The legacy converter is untouched by this.
    assert "FROM AUTHOR" in articles._markdown_to_html(SAMPLE)


def test_is_playbook_only_for_tldr_bodies():
    assert playbook_render.is_playbook(SAMPLE)
    assert not playbook_render.is_playbook(LEGACY)
    assert not playbook_render.is_playbook("")


@pytest.mark.parametrize("md", [SAMPLE, LEGACY], ids=["playbook", "legacy"])
def test_publish_html_flag_off_is_the_legacy_converter(flag, md):
    flag(False)
    assert articles._publish_html(md, SimpleNamespace(email="a@b.co")) == \
        articles._markdown_to_html(md)


def test_publish_html_flag_on_leaves_old_posts_alone(flag):
    flag(True)
    assert articles._publish_html(LEGACY, SimpleNamespace(email="a@b.co")) == \
        articles._markdown_to_html(LEGACY)


def test_publish_html_flag_on_uses_playbook_render(flag):
    flag(True)
    assert articles._publish_html(SAMPLE, SimpleNamespace(email="a@b.co")) == \
        playbook_render.to_html(SAMPLE)


def test_publish_html_falls_back_if_the_playbook_render_fails(flag, monkeypatch):
    flag(True)
    def boom(_):
        raise RuntimeError("renderer broke")
    monkeypatch.setattr(playbook_render, "to_html", boom)
    assert articles._publish_html(SAMPLE, SimpleNamespace(email="a@b.co")) == \
        articles._markdown_to_html(SAMPLE)


# ------------------------------------------------------------ §6.6 the gate
def _article(score):
    return SimpleNamespace(current_score=score, from_author_story="A real story.",
                           featured_image_alt="Clinic desk", featured_image_path="x.jpg")


def test_publish_gate_blocks_a_playbook_post_at_79_and_passes_at_80(flag):
    flag(True)
    assert any("publishing requires 80" in i
               for i in articles._blocking_issues(_article(79), 79))
    assert articles._blocking_issues(_article(80), 80) == []


def test_publish_gate_ignores_the_skim_score(flag, monkeypatch):
    flag(True)
    monkeypatch.setattr(skim, "score", lambda *a, **k: {"total_score": 0})
    assert articles._blocking_issues(_article(80), 80) == []


# ------------------------------------------------------------ §6.4 flag off
class ExplodingDb:
    def __getattr__(self, name):
        raise AssertionError(f"database touched: db.{name}")


def test_flag_off_save_ignores_blocks(flag):
    flag(False)
    articles._store_playbook_blocks(ExplodingDb(), SimpleNamespace(id="1"),
                                    {"version": 1}, SimpleNamespace(email="a@b.co"))


def test_flag_on_save_stores_blocks(flag):
    flag(True)
    calls = []
    db = SimpleNamespace(execute=lambda stmt, params: calls.append(params))
    articles._store_playbook_blocks(db, SimpleNamespace(id="1"), {"version": 1},
                                    SimpleNamespace(email="a@b.co"))
    assert calls == [{"blocks": '{"version": 1}', "id": "1"}]


def test_oversized_blocks_are_refused(flag):
    flag(True)
    db = SimpleNamespace(execute=lambda *a: None)
    with pytest.raises(Exception) as err:
        articles._store_playbook_blocks(db, SimpleNamespace(id="1"),
                                        {"x": "y" * 250_000}, SimpleNamespace(email="a"))
    assert getattr(err.value, "status_code", None) == 422


def test_enabled_for_named_logins_only(flag):
    flag(False, users=" Jai.Prajapati91@gmail.com , other@x.co")
    assert playbook.enabled_for(SimpleNamespace(email="jai.prajapati91@gmail.com"))
    assert not playbook.enabled_for(SimpleNamespace(email="seo@agenticaiautomation.co"))
    assert not playbook.enabled_for(None)
    flag(True)
    assert playbook.enabled_for(SimpleNamespace(email="anyone@x.co"))


@pytest.mark.parametrize("on,expected", [(False, "DRAFT_SYSTEM"),
                                         (True, "DRAFT_SYSTEM_PLAYBOOK")])
def test_draft_prompt_choice(monkeypatch, on, expected):
    seen = {}
    def fake_call(messages, system, **kwargs):
        seen["system"] = system
        return claude.ClaudeResult('{"title": "t"}', 1, 1, 0.0)
    monkeypatch.setattr(claude, "_call", fake_call)
    claude.generate_draft("prompt", playbook=on)
    assert seen["system"] is getattr(claude, expected)


def test_old_draft_prompt_is_unchanged_and_playbook_keeps_its_rules():
    assert claude.generate_draft.__defaults__ == (False,)
    for rule in ("Keyword density stays between 0.8% and 2%",
                 "Target Flesch-Kincaid reading ease of 60-75",
                 "Never invent a source URL",
                 "[FROM AUTHOR: 200 words on real production story about {topic}]",
                 "active voice for at least 70%"):
        assert rule in claude.DRAFT_SYSTEM and rule in claude.DRAFT_SYSTEM_PLAYBOOK
    assert "playbook_blocks" not in claude.DRAFT_SYSTEM
    assert "Never invent client names or numbers" in claude.DRAFT_SYSTEM_PLAYBOOK


# ------------------------------------------------------------ routes
@pytest.fixture
def client(flag):
    from fastapi.testclient import TestClient
    from app.database import get_db
    try:
        import app.wa_leads as wa_leads
        wa_leads.register
    except (ImportError, AttributeError):
        # The WhatsApp leads desk lives untracked on the server only
        # (docs/WA_LEADS.md); stand in for it so app.main imports here.
        import types
        stub = types.ModuleType("app.wa_leads")
        stub.register = lambda app: False
        sys.modules["app.wa_leads"] = stub
    from app.main import app
    from app.seo.deps import get_article, seo_user

    article = SimpleNamespace(id="7d2b9a52-1111-4a4a-9a9a-000000000001",
                              final_md=None, team_edit_md=SAMPLE, author_draft_md=None,
                              primary_keyword=KEYWORD)
    row = SimpleNamespace(first=lambda: ({"version": 1},))
    app.dependency_overrides[seo_user] = lambda: SimpleNamespace(email="jai@x.co")
    app.dependency_overrides[get_article] = lambda: article
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(execute=lambda *a: row)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_routes_with_flag_off(client, flag):
    flag(False)
    assert client.get("/api/seo/playbook").json() == {"enabled": False}
    aid = "7d2b9a52-1111-4a4a-9a9a-000000000001"
    assert client.get(f"/api/seo/articles/{aid}/skim").status_code == 404
    assert client.get(f"/api/seo/articles/{aid}/playbook").status_code == 404


def test_routes_with_flag_on(client, flag):
    flag(False, users="jai@x.co")
    assert client.get("/api/seo/playbook").json() == {"enabled": True}
    aid = "7d2b9a52-1111-4a4a-9a9a-000000000001"
    report = client.get(f"/api/seo/articles/{aid}/skim").json()
    assert report["total_score"] == 100 and report["advisory"] is True
    blocks = client.get(f"/api/seo/articles/{aid}/playbook").json()
    assert blocks["playbook_blocks"] == {"version": 1}


def test_existing_article_routes_still_registered(client):
    from app.main import app
    paths = app.openapi()["paths"]
    for path, method in [("/api/seo/articles/{article_id}/score", "post"),
                         ("/api/seo/articles/{article_id}/publish", "post"),
                         ("/api/seo/articles/{article_id}/write", "put"),
                         ("/api/seo/articles", "post"),
                         ("/api/seo/articles/{article_id}/skim", "get")]:
        assert method in paths.get(path, {}), path


# ------------------------------------------------------------ access from the dashboard
def _u(email, role="seo_lead", uid=1):
    return SimpleNamespace(id=uid, email=email, full_name=email.split("@")[0], role=role,
                           is_active=True)


def test_access_file_grants_named_logins(flag):
    flag(False)
    playbook.save_access(False, ["Contact@AgenticAIAutomation.co"])
    assert playbook.enabled_for(_u("contact@agenticaiautomation.co"))
    assert not playbook.enabled_for(_u("someone@else.co"))
    playbook.save_access(True, [])
    assert playbook.enabled_for(_u("someone@else.co"))
    playbook.save_access(False, [])
    assert not playbook.enabled_for(_u("contact@agenticaiautomation.co"))


def test_unreadable_access_file_means_nobody(flag):
    flag(False)
    path = Path(settings.BLOG_PLAYBOOK_ACCESS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert playbook.load_access() == {"everyone": False, "emails": []}
    assert not playbook.enabled_for(_u("contact@agenticaiautomation.co"))


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def all(self):
        return self.rows


@pytest.fixture
def admin_client(flag):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.seo.deps import admin_user
    client_fixture_app = _app_with_stub()
    users = [_u("contact@agenticaiautomation.co", "owner", 1),
             _u("updeshcredible@gmail.com", "admin", 2),
             _u("writer@agenticaiautomation.co", "seo_lead", 3)]
    db = SimpleNamespace(query=lambda model: FakeQuery(users), add=lambda e: None,
                         commit=lambda: None, rollback=lambda: None)
    client_fixture_app.dependency_overrides[admin_user] = lambda: users[0]
    client_fixture_app.dependency_overrides[get_db] = lambda: db
    yield TestClient(client_fixture_app)
    client_fixture_app.dependency_overrides.clear()


def _app_with_stub():
    try:
        import app.wa_leads as wa_leads
        wa_leads.register
    except (ImportError, AttributeError):
        import types
        stub = types.ModuleType("app.wa_leads")
        stub.register = lambda app: False
        sys.modules["app.wa_leads"] = stub
    from app.main import app
    return app


def test_admin_grants_two_logins(admin_client):
    body = {"everyone": False,
            "emails": ["contact@agenticaiautomation.co", "UpdeshCredible@gmail.com"]}
    data = admin_client.put("/api/seo/playbook/access", json=body).json()
    assert data["emails"] == ["contact@agenticaiautomation.co", "updeshcredible@gmail.com"]
    enabled = {u["email"]: u["enabled"] for u in data["users"]}
    assert enabled == {"contact@agenticaiautomation.co": True,
                       "updeshcredible@gmail.com": True,
                       "writer@agenticaiautomation.co": False}
    assert admin_client.get("/api/seo/playbook/access").json()["emails"] == data["emails"]


def test_admin_cannot_grant_unknown_login(admin_client):
    r = admin_client.put("/api/seo/playbook/access",
                         json={"everyone": False, "emails": ["stranger@x.co"]})
    assert r.status_code == 422
    assert not Path(settings.BLOG_PLAYBOOK_ACCESS_FILE).exists()


def test_access_routes_need_an_admin(flag):
    from fastapi.testclient import TestClient
    client = TestClient(_app_with_stub())
    assert client.get("/api/seo/playbook/access").status_code in (401, 403)
    assert client.put("/api/seo/playbook/access",
                      json={"everyone": True, "emails": []}).status_code in (401, 403)
