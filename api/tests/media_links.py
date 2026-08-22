"""Focused sanity + regression tests: featured image, alt text, and links.

Complements tests/e2e.py, which proves the endpoints answer. This proves the
two flows a writer actually performs end up affecting the score the way the UI
promises they will — an endpoint returning 200 is not the same as the points
landing.

The link tests assert the exact markdown the editor's toolbar emits,
`[text](url)`, so a change to the insertion format that broke scoring would
fail here rather than silently costing writers points.

    python -m tests.media_links
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5003").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "jai.prajapati91@gmail.com")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "ReviewLocal123!")

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

passed, failed = [], []
created = []


def call(method, path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read()
            if "json" not in response.headers.get("Content-Type", ""):
                return response.status, {"_bytes": len(raw)}
            return response.status, (json.loads(raw.decode()) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def upload(article_id, filename, content, content_type, token):
    boundary = "----m" + uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        f"{BASE}/api/seo/articles/{article_id}/upload-image", data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def check(name, condition, detail=""):
    (passed if condition else failed).append(name if condition else f"{name} :: {detail}")
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition and detail:
        print(f"          {detail}")


def section(title):
    print(f"\n{title}\n{'-' * len(title)}")


def param(report, key):
    """One scoring parameter from the house engine."""
    return next((p for p in report["parameters"] if p["key"] == key), None)


def rm_test(report, key):
    """One Rank Math test."""
    rank_math = report.get("rank_math") or {}
    return next((t for t in rank_math.get("tests", []) if t["key"] == key), None)


# --------------------------------------------------------------------------
status, auth = call("POST", "/auth/login",
                    payload={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
if status != 200:
    print(f"Cannot log in ({status}). Check credentials or that the API is running.")
    sys.exit(1)
token = auth["access_token"]

slug = f"media-links-{uuid.uuid4().hex[:8]}"

# Body deliberately carries every link shape the editor can produce.
BODY = """# WhatsApp automation for clinics

WhatsApp automation for clinics starts with one job: stop patients waiting for
a reply about an appointment booking.

## Why reminders come first

No-show rate is already measured by every practice, so the before-and-after is
unarguable. See [our WhatsApp service](/services#whatsapp) for scope.

## What stays with a clinician

Anything diagnostic routes to a human. Related reading:
[the industry guide](/industries) and [our case studies](/case-studies).

External sources: [WhatsApp Business API docs](https://developers.facebook.com/docs/whatsapp)
and [the n8n documentation](https://docs.n8n.io/).
"""

status, article = call("POST", "/api/seo/articles", token, {
    "type": "content",
    "vertical": "whatsapp",
    "primary_keyword": "whatsapp automation for clinics",
    "title": "WhatsApp Automation for Clinics: A Practical Guide",
    "slug": slug,
    "body_md": BODY,
    "meta_title": "WhatsApp Automation for Clinics: A Practical Guide",
    "meta_description": ("How clinics use whatsapp automation for clinics to cut "
                         "no-shows, confirm appointments and collect intake forms."),
})
if status != 201:
    print(f"Could not create the probe article ({status}): {article}")
    sys.exit(1)
article_id = article["id"]
created.append((article_id, slug))


# --------------------------------------------------------------------------
section("1. Featured image — upload, preview, replace, remove")

status, up = upload(article_id, "hero.png", PNG_1PX, "image/png", token)
check("upload returns 200", status == 200, f"got {status}: {up}")
check("upload stores a path", bool((up or {}).get("featured_image_path")))
check("first upload replaces nothing",
      (up or {}).get("replaced_previous") is False, f"got {up}")

status, img = call("GET", f"/api/seo/articles/{article_id}/image", token)
check("image reads back", status == 200, f"got {status}")
check("image bytes match what was uploaded",
      (img or {}).get("_bytes") == len(PNG_1PX),
      f"got {(img or {}).get('_bytes')} of {len(PNG_1PX)}")

status, up2 = upload(article_id, "hero2.png", PNG_1PX, "image/png", token)
check("replacing returns 200", status == 200, f"got {status}")
check("replacing removes the previous file",
      (up2 or {}).get("replaced_previous") is True,
      "old file stranded — every replace would leak one")

status, _ = call("DELETE", f"/api/seo/articles/{article_id}/image", token)
check("remove returns 200", status == 200, f"got {status}")
status, after = call("GET", f"/api/seo/articles/{article_id}", token)
check("remove clears the path", (after or {}).get("featured_image_path") is None)
status, _ = call("GET", f"/api/seo/articles/{article_id}/image", token)
check("removed image 404s", status == 404, f"got {status}")

# Put one back for the scoring checks below.
upload(article_id, "hero3.png", PNG_1PX, "image/png", token)


# --------------------------------------------------------------------------
section("2. Alt text — manual entry, persistence, and effect on score")

ALT = "Clinic counsellor reviewing WhatsApp appointment enquiries on a laptop"

status, saved = call("PUT", f"/api/seo/articles/{article_id}/write", token,
                     {"featured_image_alt": ALT})
check("alt text saves without an LLM key", status == 200, f"got {status}")
check("alt text is returned as saved",
      (saved or {}).get("featured_image_alt") == ALT,
      f"got {(saved or {}).get('featured_image_alt')!r}")

status, reread = call("GET", f"/api/seo/articles/{article_id}", token)
check("alt text persists across a reload",
      (reread or {}).get("featured_image_alt") == ALT)

status, report = call("POST", f"/api/seo/articles/{article_id}/score", token)
check("scoring succeeds with an image and alt text", status == 200, f"got {status}")

image_alt = param(report, "image_alt")
check("alt text earns points in the house scorer",
      image_alt and image_alt["points_earned"] > 0,
      f"got {image_alt}")

image_dims = param(report, "image_dimensions")
check("a 1x1 image is correctly failed on dimensions",
      image_dims and image_dims["points_earned"] == 0,
      f"1x1 must not pass the 1200x630 rule: {image_dims}")

blockers = " ".join(report.get("blocking_issues", []))
check("alt-text blocker clears once alt text is set",
      "alt caption" not in blockers.lower(), f"still blocking: {blockers}")
check("image blocker clears once an image is uploaded",
      "no featured image" not in blockers.lower(), f"still blocking: {blockers}")

# Removing the image must take the alt text with it, or the scorer would keep
# crediting alt text for an image that no longer exists.
call("DELETE", f"/api/seo/articles/{article_id}/image", token)
status, stripped = call("GET", f"/api/seo/articles/{article_id}", token)
check("removing the image clears the alt text",
      (stripped or {}).get("featured_image_alt") is None,
      f"got {(stripped or {}).get('featured_image_alt')!r}")
upload(article_id, "hero4.png", PNG_1PX, "image/png", token)
call("PUT", f"/api/seo/articles/{article_id}/write", token,
     {"featured_image_alt": ALT})


# --------------------------------------------------------------------------
section("3. Links in the text — the markdown the toolbar emits")

status, report = call("POST", f"/api/seo/articles/{article_id}/score", token)
check("scoring succeeds", status == 200, f"got {status}")

internal = param(report, "internal_links")
external = param(report, "external_links")

check("internal links are detected",
      internal and "3 internal links" in internal["detail"],
      f"expected 3 from /services#whatsapp, /industries, /case-studies: "
      f"{internal and internal['detail']}")
check("internal links earn full points",
      internal and internal["points_earned"] == internal["points_available"],
      f"got {internal}")

check("external links are detected",
      external and "2 external links" in external["detail"],
      f"expected 2: {external and external['detail']}")
check("external links earn full points",
      external and external["points_earned"] == external["points_available"],
      f"got {external}")

rm_internal = rm_test(report, "internal_links")
rm_external = rm_test(report, "external_links")
check("Rank Math passes internal links",
      rm_internal and rm_internal["passed"], f"got {rm_internal}")
check("Rank Math passes external links",
      rm_external and rm_external["passed"], f"got {rm_external}")

# An anchor link must count as internal, not be mistaken for external.
check("anchored internal link (/services#whatsapp) counts as internal",
      internal and internal["points_earned"] > 0)


# --------------------------------------------------------------------------
section("4. Link edge cases")

EDGE = """# Edge cases

Absolute same-domain: [services](https://agenticaiautomation.co/services).
Root-relative: [contact](/contact).
External: [example](https://example.com/page).
"""
call("PUT", f"/api/seo/articles/{article_id}/write", token, {"body_md": EDGE})
status, edge_report = call("POST", f"/api/seo/articles/{article_id}/score", token)

edge_internal = param(edge_report, "internal_links")
edge_external = param(edge_report, "external_links")
check("absolute same-domain URL counts as internal, not external",
      edge_internal and "2 internal links" in edge_internal["detail"],
      f"expected 2 internal: {edge_internal and edge_internal['detail']}")
check("only the genuinely external URL counts as external",
      edge_external and "1 external links" in edge_external["detail"],
      f"expected 1 external: {edge_external and edge_external['detail']}")

# A body with no links at all must lose those points, or the check is not
# actually measuring anything.
call("PUT", f"/api/seo/articles/{article_id}/write", token,
     {"body_md": "# Nothing\n\nPlain text with no links whatsoever.\n"})
status, bare = call("POST", f"/api/seo/articles/{article_id}/score", token)
bare_internal = param(bare, "internal_links")
bare_external = param(bare, "external_links")
check("no links means no internal-link points",
      bare_internal and bare_internal["points_earned"] == 0, f"got {bare_internal}")
check("no links means no external-link points",
      bare_external and bare_external["points_earned"] == 0, f"got {bare_external}")


# --------------------------------------------------------------------------
section("5. Cleanup")

for aid, aslug in created:
    status, _ = call("DELETE", f"/api/seo/articles/{aid}?confirm_slug={aslug}", token)
    check(f"probe article removed", status in (200, 404), f"got {status}")


print(f"\n{'=' * 62}")
print(f"  {len(passed)} passed, {len(failed)} failed   against {BASE}")
print(f"{'=' * 62}")
if failed:
    print("\nFailures:")
    for item in failed:
        print(f"  - {item}")
    sys.exit(1)
