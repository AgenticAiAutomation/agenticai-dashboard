"""HTML export of a finished article — tests. No database, no network.

Run:  python -m pytest tests/test_export_html.py -q
"""
import os
import sys
import types
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
from app.seo.services import export_html, storage  # noqa: E402

SAMPLE = (ROOT / "tests" / "playbook" / "sample.md").read_text(encoding="utf-8")
AID = "7d2b9a52-1111-4a4a-9a9a-000000000002"


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def all(self):
        return self.rows


def _app():
    try:
        import app.wa_leads as wa_leads
        wa_leads.register
    except (ImportError, AttributeError):
        stub = types.ModuleType("app.wa_leads")
        stub.register = lambda app: False
        sys.modules["app.wa_leads"] = stub
    from app.main import app
    return app


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.seo.deps import get_article, seo_user

    monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ENABLED", True)
    monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ACCESS_FILE", str(tmp_path / "a.json"))
    app = _app()
    faqs = [SimpleNamespace(question="Is it <safe>?", answer="Yes & quick.")]
    logged = []

    def build(score, image_path=None):
        article = SimpleNamespace(
            id=AID, current_score=score, final_md=None, team_edit_md=SAMPLE,
            author_draft_md=None, title="WhatsApp Automation for Clinics",
            primary_keyword="whatsapp automation for clinics", slug="whatsapp-clinics",
            meta_title="WhatsApp Automation for Clinics", meta_description="Cut no-shows.",
            from_author_story="We built this for a clinic.\n\nIt worked.",
            featured_image_path=image_path, featured_image_alt="Clinic desk")
        db = SimpleNamespace(query=lambda model: FakeQuery(faqs),
                             add=lambda e: logged.append(e.action),
                             commit=lambda: None, rollback=lambda: None)
        app.dependency_overrides[seo_user] = lambda: SimpleNamespace(id=1, email="a@b.co")
        app.dependency_overrides[get_article] = lambda: article
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app), logged

    yield build
    app.dependency_overrides.clear()


@pytest.mark.parametrize("score", [None, 0, 79])
def test_export_refused_below_threshold(make_client, score):
    client, logged = make_client(score)
    r = client.get(f"/api/seo/articles/{AID}/export.html")
    assert r.status_code == 409
    assert r.json()["detail"]["required"] == 80
    assert logged == []


def test_export_at_threshold_is_a_complete_light_file(make_client):
    client, logged = make_client(80)
    r = client.get(f"/api/seo/articles/{AID}/export.html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-disposition"] == 'attachment; filename="whatsapp-clinics.html"'
    doc = r.text
    assert doc.startswith("<!doctype html>")
    assert 'content="light only"' in doc and "<script" not in doc
    assert doc.count("<h1") == 1                      # the body's own H1, not a second
    assert '<blockquote class="pb-tldr">' in doc and "<table>" in doc
    assert "FROM AUTHOR" not in doc
    assert "<h2>From the author</h2><p>We built this for a clinic.</p><p>It worked.</p>" in doc
    assert "Is it &lt;safe&gt;?" in doc and "Yes &amp; quick." in doc
    assert "house score 80/100" in doc
    assert logged == ["seo.article.exported_html"]


def test_export_embeds_the_featured_image(make_client, monkeypatch):
    monkeypatch.setattr(storage, "get_object", lambda path: (b"\x89PNG", "image/png"))
    client, _ = make_client(85, image_path="local://img.png")
    doc = client.get(f"/api/seo/articles/{AID}/export.html").text
    assert '<img class="hero" src="data:image/png;base64,iVBORw==" alt="Clinic desk">' in doc


def test_export_survives_a_missing_image(make_client, monkeypatch):
    def gone(path):
        raise RuntimeError("storage down")
    monkeypatch.setattr(storage, "get_object", gone)
    client, _ = make_client(90, image_path="minio://b/k.png")
    r = client.get(f"/api/seo/articles/{AID}/export.html")
    assert r.status_code == 200 and 'class="hero"' not in r.text


def test_title_added_when_body_has_no_h1():
    doc = export_html.render(title="A <b> title", meta_title=None, meta_description=None,
                             body_html="<p>Body</p>", faqs=[], from_author_story=None,
                             score=81)
    assert "<h1>A &lt;b&gt; title</h1>" in doc and "<title>A &lt;b&gt; title</title>" in doc


def test_old_posts_are_not_given_playbook_classes():
    body = "<blockquote>\n<p><strong>Tip:</strong> x</p>\n</blockquote>\n<table></table>"
    assert export_html.style_playbook_blocks(body) == body


def test_export_does_not_touch_scoring_or_publishing():
    source = (ROOT / "api/app/seo/services/export_html.py").read_text(encoding="utf-8")
    for name in ("scoring", "rankmath", "publisher", "golive"):
        assert f"import {name}" not in source and f"services.{name}" not in source
