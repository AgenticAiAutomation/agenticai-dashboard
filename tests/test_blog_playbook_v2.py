"""Blog Playbook v2 — API-side tests. No database and no network.

Run:  python -m pytest tests/test_blog_playbook_v2.py -q
      (and node tests/playbook/v2.test.mts for the composer)

tests/playbook/sample-v2.md is the v2 composer's output; sample.v1.html is
the v1 sample rendered by the renderer as it was BEFORE v2 (generated from
feat/blog-playbook), so "same HTML as before" is checked against real output.

Covers BLOG_PLAYBOOK_V2_CHANGES.md §6.
"""
import io
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
from app.seo.services import playbook_render, publisher, skim  # noqa: E402

PLAYBOOK = ROOT / "tests" / "playbook"
V1 = (PLAYBOOK / "sample.md").read_text(encoding="utf-8")
V2 = (PLAYBOOK / "sample-v2.md").read_text(encoding="utf-8")
V1_HTML = (PLAYBOOK / "sample.v1.html").read_text(encoding="utf-8")
USER = SimpleNamespace(email="jai@x.co")


@pytest.fixture
def flags(monkeypatch, tmp_path):
    """flags(playbook, v2). Default: both off."""
    monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ACCESS_FILE", str(tmp_path / "a.json"))
    monkeypatch.setattr(settings, "BLOG_PLAYBOOK_USERS", "")
    playbook._access_cache.update(mtime=None, value=None)

    def set_flags(on: bool, v2: bool = False):
        monkeypatch.setattr(settings, "BLOG_PLAYBOOK_ENABLED", on)
        monkeypatch.setattr(settings, "BLOG_PLAYBOOK_V2", v2)
    set_flags(False)
    return set_flags


# ------------------------------------------------- old articles unchanged
def test_v1_playbook_html_is_byte_identical_with_v2_off(flags):
    flags(True, v2=False)
    assert articles._publish_html(V1, USER) == V1_HTML


def test_v1_renderer_default_is_unchanged():
    assert playbook_render.to_html(V1) == V1_HTML


def test_raw_markdown_article_uses_the_legacy_converter_even_with_v2_on(flags):
    legacy = "# Old\n\nIntro.\n\n**1. Heading**\nText with [a link](http://x.com).\n"
    flags(False)
    before = articles._publish_html(legacy, USER)
    flags(True, v2=True)
    assert articles._publish_html(legacy, USER) == before


def test_flag_off_status_and_blockers_unchanged(flags):
    flags(True, v2=False)
    article = SimpleNamespace(current_score=90, from_author_story="x",
                              featured_image_alt="alt", featured_image_path="p",
                              final_md=None, team_edit_md=V2, author_draft_md=None)
    assert articles._blocking_issues(article, 90) == []


# ------------------------------------------------------------ bold + links
def test_bold_and_links_render_in_h2_sections(flags):
    flags(True, v2=True)
    html = articles._publish_html(V2, USER)
    assert "<strong>Short answer:</strong>" in html
    assert '<a href="/pricing">pricing</a>' in html
    assert ('<a href="https://developers.facebook.com/docs/whatsapp" target="_blank" '
            'rel="noopener">') in html


def test_a_whole_bold_line_stays_bold_in_v2_not_a_heading():
    md = V2.replace("Start with the messages", "**Start here.**\n\nStart with the messages")
    assert "<p><strong>Start here.</strong></p>" in playbook_render.to_html(md, v2=True)
    # v1 keeps its old behaviour: that was the bug, and v1 output must not move.
    assert "<h3" in playbook_render.to_html(md, v2=False)


def test_javascript_links_are_dropped():
    md = V2.replace("Excludes GST.", "Excludes [GST](javascript:alert(1)).")
    html = playbook_render.to_html(md, v2=True)
    assert "javascript:" not in html and "Excludes GST" in html
    assert playbook_render.inline_html("[x](javascript:alert(1))").count("<a") == 0
    assert not playbook_render.safe_url("//evil.com")
    assert not playbook_render.safe_url("http://plain.com")


def test_faq_answers_get_bold_and_links_and_plain_json_ld():
    faq = SimpleNamespace(question="Q?", answer="It is **fast**. See [docs](https://a.com) <b>x</b>")
    v1 = articles._site_faqs([faq], v2=False)
    assert v1 == [{"question": "Q?", "answer": faq.answer}]
    (v2,) = articles._site_faqs([faq], v2=True)
    assert v2["answer"] == "It is fast. See docs <b>x</b>"          # JSON-LD text
    assert "<strong>fast</strong>" in v2["answer_html"]
    assert 'href="https://a.com" target="_blank"' in v2["answer_html"]
    assert "&lt;b&gt;" in v2["answer_html"]                        # escaped, never raw


# ---------------------------------------------------------- tables / images
def test_three_tables_with_below_text_render_in_order():
    html = playbook_render.to_html(V2, v2=True)
    order = [html.index(s) for s in ("Right after booking", "double bookings",
                                     "24 hours before", "cut no-shows the most",
                                     "When the queue slips", "our clinic guide")]
    assert order == sorted(order)


def test_inline_image_renders_as_figure_with_fixed_size():
    html = playbook_render.to_html(V2, v2=True)
    assert ('<figure class="pb-figure"><img src="/static/blog/inline/abc-123.webp" '
            'alt="Reminder on a phone" width="1536" height="1024" loading="lazy"') in html
    assert "<figcaption>A reminder</figcaption>" in html


def _image(fmt: str, size) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, fmt)
    return buffer.getvalue()


def test_webp_size_checks_real_bytes():
    assert articles.webp_size(_image("PNG", (1536, 1024))) is None      # PNG renamed .webp
    assert articles.webp_size(_image("WEBP", (1600, 1024))) == (1600, 1024)
    assert articles.webp_size(_image("WEBP", (1536, 1024))) == (1536, 1024)
    assert articles.webp_size(b"RIFF\0\0\0\0WEBPjunkjunkjunk") is None   # forged header


@pytest.fixture
def client(flags, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.database import get_db
    try:
        import app.wa_leads as wa_leads
        wa_leads.register
    except (ImportError, AttributeError):
        import types
        stub = types.ModuleType("app.wa_leads")
        stub.register = lambda app: False
        sys.modules["app.wa_leads"] = stub
    from app.main import app
    from app.seo.deps import get_article, seo_user

    stored = {}
    monkeypatch.setattr(settings, "SITE_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(articles.storage, "put_object", lambda aid, c, m: (
        stored.setdefault("path", f"file:///x/{aid}/{'a' * 32}.webp")))
    monkeypatch.setattr(articles.storage, "delete_object", lambda p: stored.pop("path", None) == p)
    monkeypatch.setattr(articles, "log_event", lambda *a, **k: None)

    article = SimpleNamespace(id="7d2b9a52-1111-4a4a-9a9a-000000000001", status="draft",
                              featured_image_path="featured.jpg")
    app.dependency_overrides[seo_user] = lambda: USER
    app.dependency_overrides[get_article] = lambda: article
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(commit=lambda: None)
    yield TestClient(app), article, tmp_path, stored
    app.dependency_overrides.clear()


def test_inline_upload_route(client, flags):
    http, article, tmp, stored = client
    url = f"/api/seo/articles/{article.id}/upload-inline-image"
    flags(True, v2=False)
    assert http.post(url, files={"file": ("a.webp", b"x")}).status_code == 404

    flags(True, v2=True)
    for bad in (_image("PNG", (1536, 1024)), _image("WEBP", (1600, 1024))):
        r = http.post(url, files={"file": ("a.webp", bad, "image/webp")})
        assert r.status_code == 400
        assert r.json()["detail"] == "Upload a WebP image of exactly 1536 × 1024."

    r = http.post(url, files={"file": ("a.webp", _image("WEBP", (1536, 1024)), "image/webp")})
    assert r.status_code == 200, r.text
    public = r.json()["url"]
    assert public == f"/static/blog/inline/{article.id}-{'a' * 32}.webp"
    assert (tmp / "media" / "inline" / public.rsplit("/", 1)[1]).exists()
    assert article.featured_image_path == "featured.jpg"              # untouched

    monkeypatch_path = public  # removing the item deletes both files
    r = http.delete(f"/api/seo/articles/{article.id}/inline-image",
                    params={"url": monkeypatch_path})
    assert r.json()["file_removed"] is True
    assert not (tmp / "media" / "inline" / public.rsplit("/", 1)[1]).exists()

    other = public.replace("7d2b9a52", "00000000")
    assert http.delete(f"/api/seo/articles/{article.id}/inline-image",
                       params={"url": other}).status_code == 422


# ----------------------------------------------------------------- callout
def _blockers(md):
    return articles._playbook_blocking_issues(md)


def test_callout_blocker(flags):
    flags(True, v2=True)
    assert _blockers(V2) == []                                          # 1, custom label
    none = V2.replace("> **Clinic hack:** Keep your **old number** on the API.\n\n", "")
    assert _blockers(none) == ["Add one callout before submitting."]
    two = V2.replace("Excludes GST.", "Excludes GST.\n\n> **Note:** second one.")
    assert _blockers(two) == ["Only one callout per article."]
    # A reserved label is not a callout, so the rule still asks for one.
    reserved = V2.replace("**Clinic hack:**", "**Before:**")
    assert _blockers(reserved) == ["Add one callout before submitting."]


def test_half_filled_blocks_block(flags):
    flags(True, v2=True)
    no_alt = V2.replace("![Reminder on a phone]", "![]")
    assert "An inline image has no alt text." in _blockers(no_alt)
    no_numbers = (V2.replace("18% of patients did not turn up.", "many did not turn up.")
                  .replace("18% to 7% in 14 days", "fewer").replace("60 a day to 5 a day", "less"))
    assert "A real example has no numbers." in _blockers(no_numbers)
    bad_link = V2.replace("(/pricing)", "(javascript:alert(1))")
    assert any("Links must be" in i for i in _blockers(bad_link))


def test_blockers_ignore_raw_markdown_articles(flags):
    flags(True, v2=True)
    assert _blockers("# Old\n\n## H\n\nText.\n") == []


# -------------------------------------------------------------------- skim
def test_skim_skips_absent_optional_blocks():
    full = skim.score(V2, "whatsapp automation for clinics")
    stripped = V2
    start = stripped.index("> **Real example:**")
    end = stripped.index("[FROM AUTHOR")
    stripped = stripped[:start] + stripped[end:]
    for table_start in [i for i in range(len(stripped)) if stripped.startswith("| Message", i)][::-1]:
        table_end = stripped.index("\n\n", table_start)
        stripped = stripped[:table_start] + stripped[table_end + 2:]
    assert "|" not in stripped and "Real example" not in stripped

    lean = skim.score(stripped, "whatsapp automation for clinics")
    skipped = {c["key"] for c in lean["checks"] if c.get("skipped")}
    assert skipped == {"real_example", "table"}
    assert len(lean["parameters_skipped"]) == 2
    others = [c for c in lean["checks"] if not c.get("skipped")]
    if all(c["passed"] for c in others):
        assert lean["total_score"] == 100
    # Same percentage as full marks on the rest: earned / available.
    assert lean["total_score"] == round(sum(c["points_earned"] for c in others)
                                        / sum(c["points_available"] for c in others) * 100)
    assert full["parameters_skipped"] == []


def test_skim_present_real_example_still_scored_partially():
    md = V2.replace("18% to 7% in 14 days", "fewer").replace("60 a day to 5 a day", "less") \
           .replace("18% of patients", "many patients")
    check = next(c for c in skim.score(md)["checks"] if c["key"] == "real_example")
    assert not check.get("skipped") and check["points_earned"] == 5


# ------------------------------------------------------------ author extras
def test_author_extras_clean_and_site_shape():
    assert articles._site_author_extras(playbook.clean_author_extras({})) is None
    extras = playbook.clean_author_extras({
        "best_pick": {"option": "WATI", "reason": "**cheapest** for clinics"},
        "notice": "Prices change; see [Meta](https://meta.com).",
        "must_do": ["Verify your business", " ", "Export chats first"],
    })
    assert extras["must_do"] == ["Verify your business", "Export chats first"]
    site = articles._site_author_extras(extras)
    assert site["best_pick"]["option"] == "WATI"
    assert "<strong>cheapest</strong>" in site["best_pick"]["reason_html"]
    assert 'target="_blank"' in site["notice_html"]
    assert len(site["must_do_html"]) == 2
    with pytest.raises(ValueError):
        playbook.clean_author_extras({"must_do": ["x"] * 6})


def test_publisher_writes_extras_only_when_given(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SITE_CONTENT_DIR", str(tmp_path))
    import json
    common = dict(article_id="1", title="T", html="<p>x</p>", meta_title=None,
                  meta_description=None, primary_keyword="k", featured_image_path=None,
                  featured_image_alt=None, author="A", from_author_story="s")
    publisher.publish(slug="a", faqs=[{"question": "Q", "answer": "A"}], **common)
    doc = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert "author_extras" not in doc and doc["faqs"] == [{"question": "Q", "answer": "A"}]
    publisher.publish(slug="b", faqs=[{"question": "Q", "answer": "A", "answer_html": "<p>A</p>"}],
                      author_extras={"notice_html": "<p>n</p>"}, **common)
    doc = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert doc["author_extras"] == {"notice_html": "<p>n</p>"}
    assert doc["faqs"][0]["answer_html"] == "<p>A</p>"
