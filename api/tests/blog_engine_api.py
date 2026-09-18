"""Blog Visual Engine — block endpoints, end to end over HTTP.

Needs a running API with BLOG_ENGINE_V2=true against a disposable database.
Every object it creates is deleted on the way out.

    BASE_URL=http://127.0.0.1:5005 OWNER_EMAIL=... OWNER_PASSWORD=... \
        python -m tests.blog_engine_api
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5005").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@blogengine-test.dev")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "OwnerTest123!x")
CONTENT_DIR = os.environ.get("SITE_CONTENT_DIR", "")

passed, failed = [], []


def check(name, condition, detail=""):
    (passed if condition else failed).append(name)
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"   {detail}" if detail and not condition else ""))


def call(method, path, token=None, payload=None, raw=None, content_type="application/json"):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body.decode(errors="replace")


def multipart(field, filename, content, mime):
    boundary = "----blogengine" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


print(f"against {BASE}\n")
status, login = call("POST", "/auth/login", payload={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
assert status == 200, f"login failed: {status} {login}"
token = login["access_token"]

from app.blog_engine.fixtures import __path__ as _fx  # noqa: E402
with open(os.path.join(_fx[0], "sample-article.json"), "r", encoding="utf-8") as fh:
    fixture = json.load(fh)

print("1. Create an article and save blocks\n" + "-" * 50)
slug = f"blocks-e2e-{uuid.uuid4().hex[:8]}"
status, article = call("POST", "/api/seo/articles", token, {
    "type": "content", "vertical": "rpa", "primary_keyword": "invoice processing automation",
    "title": fixture["meta"]["title"], "slug": slug, "body_md": "# draft\n\nplaceholder\n",
    "meta_title": fixture["meta"]["meta_title"], "meta_description": fixture["meta"]["meta_description"],
    "from_author_story": "story " * 130,
})
check("article created", status == 201, f"{status}: {article}")
aid = article["id"]

status, got = call("GET", f"/api/seo/articles/{aid}/blocks", token)
check("GET blocks on a legacy article: format legacy, empty", status == 200 and got["content_format"] == "legacy" and got["blocks"] == [], f"{status}: {got}")
check("owner can edit and publish", got["can_edit"] and got["can_publish"])
check("author name comes from config", bool(got["author_name"]))

status, saved = call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": fixture["blocks"], "note": "first save"})
check("PUT blocks saves", status == 200 and saved["saved"], f"{status}: {saved}")
check("first save is revision 1", saved["revision_number"] == 1)
check("report has word count and visuals", saved["report"]["word_count"] > 500 and saved["report"]["visuals"] >= 10)
check("no blocking validators on the fixture", saved["report"]["blocking"] == 0, saved["report"]["violations"])
check("markdown projection produced", saved["markdown_words"] > 800)

status, got = call("GET", f"/api/seo/articles/{aid}/blocks", token)
check("format now blocks, blocks round-trip", got["content_format"] == "blocks" and len(got["blocks"]) == len(fixture["blocks"]))
status, detail = call("GET", f"/api/seo/articles/{aid}", token)
check("team_edit_md is the projection (scorer sees it)", "Key takeaways" in (detail.get("team_edit_md") or ""))
check("FAQ table synced from the faq block", len(detail.get("faqs") or []) == 5, len(detail.get("faqs") or []))

print("\n2. Validation errors name the block\n" + "-" * 50)
bad = [{"id": "blk_bad1", "type": "image", "attrs": {"src": "/x/a.jpg", "alt": "", "width": 1, "height": 1}}]
status, err = call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": bad})
check("invalid block -> 422 with block_id", status == 422 and err["detail"]["block_id"] == "blk_bad1", f"{status}: {err}")
status, got = call("GET", f"/api/seo/articles/{aid}/blocks", token)
check("a rejected save changes nothing", len(got["blocks"]) == len(fixture["blocks"]))

print("\n3. Revisions\n" + "-" * 50)
status, same = call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": fixture["blocks"]})
check("identical save creates no revision", same["changed"] is False and same["revision_number"] == 1)
edited = json.loads(json.dumps(fixture["blocks"]))
edited[1]["content"] = [{"text": "Edited lead paragraph."}]
status, second = call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": edited, "note": "edit lead"})
check("changed save creates revision 2", second["revision_number"] == 2 and second["changed"])
status, revs = call("GET", f"/api/seo/articles/{aid}/blocks/revisions", token)
check("two revisions listed, newest first", status == 200 and [r["revision_number"] for r in revs] == [2, 1], revs)
check("revision carries note and author", revs[0]["note"] == "edit lead" and revs[0]["created_by"])
status, restored = call("POST", f"/api/seo/articles/{aid}/blocks/revisions/1/restore", token)
check("restore creates revision 3 with the old content", status == 200 and restored["revision_number"] == 3, f"{status}: {restored}")
status, got = call("GET", f"/api/seo/articles/{aid}/blocks", token)
check("restored content matches revision 1", got["blocks"][1]["content"][0]["text"].startswith("Every automation vendor"))
status, err = call("POST", f"/api/seo/articles/{aid}/blocks/revisions/99/restore", token)
check("unknown revision -> 404", status == 404)

print("\n4. Preview\n" + "-" * 50)
status, prev = call("POST", f"/api/seo/articles/{aid}/blocks/preview", token, {"blocks": fixture["blocks"], "title": "Preview title only"})
check("preview returns a full page", status == 200 and prev["html"].startswith("<!DOCTYPE html>"))
check("preview uses the unsaved title", "Preview title only" in prev["html"])
check("preview carries no analytics script", "gtag/js" not in prev["html"] and "gtag(" not in prev["html"])
check("preview has the author box with the configured name", got["author_name"] in prev["html"])

print("\n5. Media upload\n" + "-" * 50)
from PIL import Image  # noqa: E402
buf = io.BytesIO()
img = Image.new("RGB", (1800, 1000), (255, 90, 0))
img.save(buf, "JPEG", quality=90, exif=b"Exif\x00\x00II*\x00\x08\x00\x00\x00\x00\x00\x00\x00")
body, ctype = multipart("file", "photo.jpg", buf.getvalue(), "image/jpeg")
status, up = call("POST", "/api/seo/media/upload", token, raw=body, content_type=ctype)
check("jpeg upload accepted", status == 200 and up["src"].startswith("/static/blog/uploads/"), f"{status}: {up}")
check("upload resized to 2400 max and dims returned", up["width"] == 1800 and up["height"] == 1000)
svg = b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'></svg>"
body, ctype = multipart("file", "evil.svg", svg, "image/svg+xml")
status, up2 = call("POST", "/api/seo/media/upload", token, raw=body, content_type=ctype)
check("svg rejected", status == 415, f"{status}: {up2}")
body, ctype = multipart("file", "fake.jpg", b"not an image at all", "image/jpeg")
status, up3 = call("POST", "/api/seo/media/upload", token, raw=body, content_type=ctype)
check("mime is sniffed, not trusted", status == 415, f"{status}: {up3}")

print("\n6. Publish gates\n" + "-" * 50)
status, err = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {})
check("score below 80 blocks publishing", status == 409 and err["detail"]["error"] == "score_below_threshold", f"{status}: {err}")

# Force the score and the legacy blockers past, as admin_ops.py does.
import app.models  # noqa: F401,E402
from app.database import SessionLocal  # noqa: E402
from app.seo.models import SeoArticle  # noqa: E402
session = SessionLocal()
row = session.query(SeoArticle).filter(SeoArticle.id == uuid.UUID(aid)).first()
row.current_score = 91
session.commit()
session.close()
status, err = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {})
check("legacy blockers still apply (no featured image)", status == 409 and err["detail"]["error"] == "blocking_issues", f"{status}: {err}")

buf = io.BytesIO(); Image.new("RGB", (1200, 630), (10, 9, 8)).save(buf, "JPEG")
body, ctype = multipart("file", "hero.jpg", buf.getvalue(), "image/jpeg")
status, _ = call("POST", f"/api/seo/articles/{aid}/upload-image", token, raw=body, content_type=ctype)
check("featured image uploaded", status == 200, status)
call("PUT", f"/api/seo/articles/{aid}/write", token, {"featured_image_alt": "Orchestrator queue before the handoff"})

# A blocking validator: heading skip h2 -> h4.
skip = [{"id": "blk_sk01", "type": "heading", "attrs": {"level": 2}, "content": "A"},
        {"id": "blk_sk02", "type": "heading", "attrs": {"level": 4}, "content": "B"},
        {"id": "blk_sk03", "type": "paragraph", "content": "body"}]
call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": skip})
status, err = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {})
check("blocking validator stops publish", status == 409 and err["detail"]["error"] == "validators_blocking", f"{status}: {err}")
status, err = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {"override_reason": "short"})
check("override reason must be substantive", status == 422)
status, pub = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {"override_reason": "Client demo needs this live; heading fix follows tomorrow."})
check("admin override publishes and reports what was overridden", status == 200 and pub["overridden"], f"{status}: {pub}")

print("\n7. Publish output\n" + "-" * 50)
call("PUT", f"/api/seo/articles/{aid}/blocks", token, {"blocks": fixture["blocks"]})
status, pub = call("POST", f"/api/seo/articles/{aid}/blocks/publish", token, {})
check("clean publish succeeds", status == 200 and pub["published"], f"{status}: {pub}")
check("nothing overridden", pub["overridden"] == [])
if CONTENT_DIR:
    page = os.path.join(CONTENT_DIR, slug, "index.html")
    rec = os.path.join(CONTENT_DIR, f"{slug}.json")
    check("index.html written", os.path.isfile(page))
    check("legacy JSON record written alongside", os.path.isfile(rec))
    doc = json.load(open(rec, encoding="utf-8"))
    check("JSON carries content_format=blocks and is not a draft", doc.get("content_format") == "blocks" and doc["is_draft"] is False)
    check("JSON html is the rendered body (legacy fallback)", "b-takeaways" in doc["html"])
    html = open(page, encoding="utf-8").read()
    check("page has the hero as fetchpriority=high", 'fetchpriority="high"' in html and f"/static/blog/{slug}" in html)
    check("page author is a Person with credentials (JSON-LD)", '"@type": "Person"' in html and "hasCredential" in html)
    check("page is not marked draft", "Draft preview" not in html and "noindex" not in html)
    css_files = os.listdir(os.path.join(os.path.dirname(CONTENT_DIR), "media", "engine"))
    check("deferred stylesheet written once", len(css_files) == 1 and css_files[0].startswith("blog-engine."))
status, detail = call("GET", f"/api/seo/articles/{aid}", token)
check("article status published", detail["status"] == "published")

print("\n8. Role gates\n" + "-" * 50)
status, u = call("POST", "/users", token, {"email": f"lead-{uuid.uuid4().hex[:6]}@blogengine-test.dev", "full_name": "Lead", "role": "seo_lead", "password": "LeadTest123!x"})
if status in (200, 201):
    pw = u.get("generated_password") or "LeadTest123!x"
    s2, l2 = call("POST", "/auth/login", payload={"email": u["email"], "password": pw})
    if s2 == 200:
        t2 = l2["access_token"]
        status, g2 = call("GET", f"/api/seo/articles/{aid}/blocks", t2)
        check("seo_lead can read and edit but not publish", status == 200 and g2["can_edit"] and not g2["can_publish"])
        status, _ = call("POST", f"/api/seo/articles/{aid}/blocks/publish", t2, {})
        check("seo_lead publish -> 403", status == 403, status)
        call("DELETE", f"/users/{u['id']}", token)
    else:
        print("  skip  (could not log in as the created user)")
else:
    print(f"  skip  (user creation endpoint returned {status})")

print("\n9. Cleanup\n" + "-" * 50)
status, _ = call("POST", f"/api/seo/articles/{aid}/unpublish", token)
status, _ = call("DELETE", f"/api/seo/articles/{aid}?confirm_slug={slug}", token)
check("article removed", status in (200, 204, 404), status)
if CONTENT_DIR:
    page_dir = os.path.join(CONTENT_DIR, slug)
    if os.path.isdir(page_dir):
        import shutil
        shutil.rmtree(page_dir, ignore_errors=True)

print("\n" + "=" * 60)
print(f"  {len(passed)} passed, {len(failed)} failed   against {BASE}")
sys.exit(1 if failed else 0)
