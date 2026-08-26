"""Admin operations on a PUBLISHED article: edit, republish, unpublish, delete."""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date

API = "http://127.0.0.1:5003"
PUB = r"C:\Users\hp\Documents\agenticai-dashboard\published\articles"
APPROVAL = r"C:\Users\hp\Documents\agenticai-dashboard\api\SEO_LIVE_APPROVED.txt"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")

passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name if ok else f"{name} :: {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok and detail:
        print(f"          {detail}")


def call(method, path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
            return response.status, (json.loads(body.decode()) if body else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def upload_image(article_id, token):
    boundary = "----a" + uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="hero.png"\r\n',
        b"Content-Type: image/png\r\n\r\n",
        PNG,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        f"{API}/api/seo/articles/{article_id}/upload-image", data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status


token = call("POST", "/auth/login", payload={
    "email": "jai.prajapati91@gmail.com", "password": "ReviewLocal123!"})[1]["access_token"]

with open(APPROVAL, "w", encoding="utf-8") as fh:
    fh.write(f"GO LIVE {date.today().isoformat()}\n")

slug = f"admin-ops-{uuid.uuid4().hex[:8]}"
status, article = call("POST", "/api/seo/articles", token, {
    "type": "content", "vertical": "whatsapp",
    "primary_keyword": "admin ops check", "title": "Admin Ops Check",
    "slug": slug, "body_md": "# Heading\n\nBody text here.\n",
    "meta_title": "Admin Ops Check", "meta_description": "x" * 150,
    "from_author_story": "story " * 130,
})
article_id = article["id"]
upload_image(article_id, token)
call("PUT", f"/api/seo/articles/{article_id}/write", token,
     {"featured_image_alt": "alt text"})

# Force past the score gate; publishing mechanics are what is under test here.
sys.path.insert(0, r"C:\Users\hp\Documents\agenticai-dashboard\api")
import app.models  # noqa: F401,E402
from app.database import SessionLocal  # noqa: E402
from app.seo.models import SeoArticle  # noqa: E402

session = SessionLocal()
row = session.query(SeoArticle).filter(SeoArticle.id == article_id).first()
row.current_score = 95
session.commit()
session.close()

print("\n1. Publish live\n" + "-" * 46)
status, result = call("POST", f"/api/seo/articles/{article_id}/publish", token)
check("publishes live", status == 200 and (result or {}).get("wp_status") == "publish",
      f"{status}: {result}")
check("IndexNow reported in the response",
      "IndexNow" in ((result or {}).get("message") or ""), (result or {}).get("message"))
first = json.load(open(os.path.join(PUB, f"{slug}.json"), encoding="utf-8"))

print("\n2. Edit while published\n" + "-" * 46)
status, saved = call("PUT", f"/api/seo/articles/{article_id}/write", token,
                     {"title": "Admin Ops Check (corrected)"})
check("a published article can be edited", status == 200, f"{status}: {saved}")
check("it stays published while being corrected",
      (saved or {}).get("status") == "published", f"got {(saved or {}).get('status')}")

status, blocked = call("PUT", f"/api/seo/articles/{article_id}/write", token,
                       {"slug": "some-other-slug"})
check("its live URL cannot be changed", status == 409, f"got {status}")

print("\n3. Republish refreshes the updated date\n" + "-" * 46)
status, result = call("POST", f"/api/seo/articles/{article_id}/publish", token)
second = json.load(open(os.path.join(PUB, f"{slug}.json"), encoding="utf-8"))
check("republish succeeds", status == 200, f"{status}")
check("updated_at moves forward", second["updated_at"] > first["updated_at"],
      f"{first['updated_at']} -> {second['updated_at']}")
check("published_at is preserved", second["published_at"] == first["published_at"],
      "the original publication date must not be rewritten")
check("the edit reached the published file", "corrected" in second["title"],
      second["title"])

print("\n4. Unpublish\n" + "-" * 46)
status, _ = call("POST", f"/api/seo/articles/{article_id}/unpublish", token)
check("unpublish succeeds", status == 200, f"got {status}")
check("file removed from the site",
      not os.path.isfile(os.path.join(PUB, f"{slug}.json")))
status, back = call("GET", f"/api/seo/articles/{article_id}", token)
check("record survives and returns to team review",
      (back or {}).get("status") == "in_team_review", f"got {(back or {}).get('status')}")

print("\n5. Delete while published\n" + "-" * 46)
call("POST", f"/api/seo/articles/{article_id}/publish", token)
check("republished for the delete test",
      os.path.isfile(os.path.join(PUB, f"{slug}.json")))

status, _ = call("DELETE", f"/api/seo/articles/{article_id}?confirm_slug=nope", token)
check("wrong slug still refused", status == 400, f"got {status}")
check("still live after a refused delete",
      os.path.isfile(os.path.join(PUB, f"{slug}.json")))

status, gone = call("DELETE", f"/api/seo/articles/{article_id}?confirm_slug={slug}",
                    token)
check("a published article can now be deleted", status == 200, f"{status}: {gone}")
check("it was taken off the site first",
      not os.path.isfile(os.path.join(PUB, f"{slug}.json")),
      "the live file must go before the record does")
status, _ = call("GET", f"/api/seo/articles/{article_id}", token)
check("record is gone", status == 404, f"got {status}")

if os.path.exists(APPROVAL):
    os.remove(APPROVAL)

print(f"\n{'=' * 60}\n  {len(passed)} passed, {len(failed)} failed\n{'=' * 60}")
for item in failed:
    print(f"  - {item}")
sys.exit(1 if failed else 0)
