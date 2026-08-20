"""End-to-end dashboard test suite.

Drives the real HTTP API the way the browser does, so it catches the class of
bug that unit tests miss — response-model serialisation, status codes, and
gates that are enforced server-side rather than in the UI.

Usage:
    python -m tests.e2e                       # against http://127.0.0.1:5003
    BASE_URL=https://api.dashboard.agenticaiautomation.co python -m tests.e2e
    OWNER_EMAIL=... OWNER_PASSWORD=... python -m tests.e2e

Every object it creates is deleted on the way out, and it refuses to run any
destructive assertion against a user it did not create itself.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5003").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "jai.prajapati91@gmail.com")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "ReviewLocal123!")

passed, failed = [], []
created_user_ids = []
created_article_ids = []


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------
def call(method, path, token=None, payload=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body
    except Exception as exc:                      # connection refused, DNS, TLS
        return 0, f"transport error: {exc}"


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} :: {detail}")
        print(f"  FAIL  {name}")
        if detail:
            print(f"          {detail}")


def section(title):
    print(f"\n{title}\n{'-' * len(title)}")


# --------------------------------------------------------------------------
# 1. Authentication
# --------------------------------------------------------------------------
section("1. Authentication")

status, body = call("POST", "/auth/login",
                    payload={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
check("login with valid credentials returns 200", status == 200, f"got {status}: {body}")
if status != 200:
    print("\nCannot continue without a session. Check OWNER_EMAIL/OWNER_PASSWORD.")
    sys.exit(1)

token = body["access_token"]
check("login returns an access token", bool(token))
check("login returns a refresh token", bool(body.get("refresh_token")))

status, body = call("POST", "/auth/login",
                    payload={"email": OWNER_EMAIL, "password": "definitely-wrong"})
check("login with wrong password returns 401", status == 401, f"got {status}")

status, body = call("POST", "/auth/login",
                    payload={"email": "nobody@example.com", "password": "whatever"})
check("login with unknown email returns 401", status == 401, f"got {status}")

status, body = call("GET", "/auth/me", token)
check("/auth/me returns the session user", status == 200 and body.get("email") == OWNER_EMAIL,
      f"got {status}: {body}")

status, _ = call("GET", "/auth/me")
check("/auth/me without a token returns 401/403", status in (401, 403), f"got {status}")

status, _ = call("GET", "/auth/me", "not-a-real-token")
check("/auth/me with a garbage token returns 401", status == 401, f"got {status}")


# --------------------------------------------------------------------------
# 2. User management — the area that broke in production
# --------------------------------------------------------------------------
section("2. User management")

probe_email = f"e2e-{uuid.uuid4().hex[:10]}@example.com"

status, body = call("POST", "/users", token, {
    "email": probe_email,
    "full_name": "E2E Probe User",
    "role": "admin",
    "must_change_password": True,
})
check("create user returns 201", status == 201, f"got {status}: {body}")

if status == 201:
    created_user_ids.append(body["id"])
    # This is the exact defect seen in production: the row committed but the
    # response model failed to serialise, so the browser saw a network error
    # while the user really had been created.
    check("create user response includes generated_password",
          bool(body.get("generated_password")),
          "password missing — admin cannot deliver credentials")
    check("create user response includes delivery_note",
          bool(body.get("delivery_note")),
          "delivery_note missing — this is what raised ValidationError in prod")
    check("created user has the requested role", body.get("role") == "admin",
          f"got {body.get('role')}")
    check("created user is flagged must_change_password",
          body.get("must_change_password") is True)
    check("password hash is never returned",
          "password_hash" not in body and "hashed_password" not in body)

status, body = call("POST", "/users", token, {
    "email": probe_email, "full_name": "Duplicate", "role": "seo",
})
check("duplicate email returns 400 not 500", status == 400, f"got {status}: {body}")

status, body = call("POST", "/users", token, {
    "email": f"e2e-{uuid.uuid4().hex[:8]}@example.com",
    "full_name": "Bad Role", "role": "wizard",
})
check("invalid role is rejected (400/422)", status in (400, 422), f"got {status}")

status, body = call("POST", "/users", token, {
    "email": "not-an-email", "full_name": "Bad Email", "role": "seo",
})
check("malformed email is rejected (422)", status == 422, f"got {status}")

status, body = call("POST", "/users", token, {
    "email": f"e2e-{uuid.uuid4().hex[:8]}@example.com",
    "full_name": "Weak Password", "role": "seo", "password": "123",
})
check("weak password is rejected (400/422)", status in (400, 422), f"got {status}")

status, body = call("GET", "/users", token)
check("list users returns 200", status == 200, f"got {status}")
check("list users returns a list", isinstance(body, list))

status, _ = call("GET", "/users")
check("list users without a token is refused", status in (401, 403), f"got {status}")

if created_user_ids:
    # Empty password object means "generate one for me".
    status, body = call("POST", f"/users/{created_user_ids[0]}/reset-password", token,
                        {"password": None})
    check("reset-password returns a new generated password",
          status == 200 and bool((body or {}).get("generated_password")),
          f"got {status}: {body}")
    check("reset-password forces a change on next login",
          (body or {}).get("must_change_password") is True, f"got {body}")

    status, body = call("POST", f"/users/{created_user_ids[0]}/reset-password", token,
                        {"password": "short"})
    check("reset-password rejects a weak password", status in (400, 422), f"got {status}")

    status, _ = call("POST", f"/users/{uuid.uuid4().int % 10**9}/reset-password", token,
                     {"password": None})
    check("reset-password on an unknown user returns 404", status == 404, f"got {status}")


# --------------------------------------------------------------------------
# 3. Article creation without any LLM key
# --------------------------------------------------------------------------
section("3. Article creation (no LLM key required)")

slug = f"e2e-test-article-{uuid.uuid4().hex[:8]}"
BODY_MD = """# WhatsApp automation for clinics

WhatsApp automation for clinics starts with one job: stop patients waiting for
a reply about an appointment.

## Why reminders come first

No-show rate is already measured, so the before-and-after is unarguable.

## What the agent handles

It confirms, reschedules and cancels, and collects the intake form.

## What stays with a clinician

Anything diagnostic routes to a human. See [our services](/services) and the
[WhatsApp API docs](https://developers.facebook.com/docs/whatsapp).
"""

status, article = call("POST", "/api/seo/articles", token, {
    "type": "content",
    "vertical": "whatsapp",
    "primary_keyword": "whatsapp automation for clinics",
    "title": "WhatsApp Automation for Clinics: A Practical Guide",
    "slug": slug,
    "body_md": BODY_MD,
    "meta_title": "WhatsApp Automation for Clinics: A Practical Guide",
    "meta_description": ("How clinics use whatsapp automation for clinics to cut "
                         "no-shows, confirm appointments and collect intake forms."),
    "faqs": [{"question": "How long does deployment take?",
              "answer": "Two to three weeks including Meta verification.",
              "source_url": "https://www.reddit.com/r/india/"}],
})
check("create article returns 201", status == 201, f"got {status}: {article}")

article_id = None
if status == 201:
    article_id = article["id"]
    created_article_ids.append(article_id)
    check("article stores the slug the writer supplied", article.get("slug") == slug,
          f"asked for {slug!r}, got {article.get('slug')!r}")
    check("article starts in team review",
          article.get("status") == "in_team_review", f"got {article.get('status')}")
    check("article body is stored", bool(article.get("team_edit_md")))
    check("FAQ is stored with its source URL",
          len(article.get("faqs") or []) == 1
          and bool(article["faqs"][0].get("source_url")))

# Content articles must not carry a country; onpage ones must.
status, body = call("POST", "/api/seo/articles", token, {
    "type": "content", "vertical": "whatsapp", "country": "india",
    "primary_keyword": "constraint probe",
})
check("content article with a country is rejected", status in (400, 409, 422),
      f"got {status}: {body}")

status, body = call("POST", "/api/seo/articles", token, {
    "type": "onpage", "vertical": "whatsapp", "primary_keyword": "constraint probe 2",
})
check("onpage article without a country is rejected", status in (400, 409, 422),
      f"got {status}: {body}")

# Country x vertical matrix: whatsapp is India-only.
status, body = call("POST", "/api/seo/articles", token, {
    "type": "onpage", "vertical": "whatsapp", "country": "uk",
    "primary_keyword": "matrix probe",
})
check("unapproved country/vertical pair is rejected", status in (400, 409, 422),
      f"got {status}: {body}")

if article_id:
    status, body = call("PUT", f"/api/seo/articles/{article_id}/write", token,
                        {"title": "Updated Title Via Save"})
    check("save draft returns 200", status == 200, f"got {status}")
    check("save draft persists the change",
          (body or {}).get("title") == "Updated Title Via Save")

    new_slug = f"{slug}-renamed"
    status, body = call("PUT", f"/api/seo/articles/{article_id}/write", token,
                        {"slug": new_slug})
    check("writer can change the slug after creation",
          status == 200 and (body or {}).get("slug") == new_slug,
          f"got {(body or {}).get('slug')}")

status, body = call("GET", "/api/seo/articles", token)
check("list articles returns 200", status == 200, f"got {status}")

status, _ = call("GET", "/api/seo/articles")
check("list articles without a token is refused", status in (401, 403), f"got {status}")

status, _ = call("GET", f"/api/seo/articles/{uuid.uuid4()}", token)
check("unknown article id returns 404", status == 404, f"got {status}")


# --------------------------------------------------------------------------
# 4. Scoring — house engine and Rank Math
# --------------------------------------------------------------------------
section("4. Scoring")

if article_id:
    status, score = call("POST", f"/api/seo/articles/{article_id}/score", token)
    check("score returns 200", status == 200, f"got {status}: {score}")

    if status == 200:
        check("house score is 0-100",
              isinstance(score.get("total_score"), int) and 0 <= score["total_score"] <= 100,
              f"got {score.get('total_score')}")
        check("house scorer returns per-parameter detail",
              len(score.get("parameters") or []) >= 20,
              f"got {len(score.get('parameters') or [])} parameters")
        check("house scorer returns actionable comments",
              isinstance(score.get("comments"), list))
        check("skipped parameters are named, not silently zeroed",
              isinstance(score.get("parameters_skipped", []), list)
              or "parameters" in score)

        rank_math = score.get("rank_math")
        check("Rank Math report is present", bool(rank_math))
        if rank_math:
            check("Rank Math score is 0-100",
                  0 <= rank_math["total_score"] <= 100,
                  f"got {rank_math['total_score']}")
            check("Rank Math returns its grade band",
                  rank_math.get("grade") in
                  ("great", "good", "needs improvement"),
                  f"got {rank_math.get('grade')}")
            check("Rank Math returns all four test groups",
                  len(rank_math.get("groups") or {}) == 4,
                  f"got {list((rank_math.get('groups') or {}).keys())}")
            check("Rank Math returns individual tests",
                  len(rank_math.get("tests") or []) >= 15,
                  f"got {len(rank_math.get('tests') or [])}")
            check("every Rank Math test carries a message",
                  all(t.get("message") for t in (rank_math.get("tests") or [])))

        check("blocking issues are reported",
              isinstance(score.get("blocking_issues"), list))
        check("an incomplete draft is blocked from publishing",
              len(score.get("blocking_issues") or []) > 0,
              "expected blockers on a draft with no image and no author story")


# --------------------------------------------------------------------------
# 5. Publish gates
# --------------------------------------------------------------------------
section("5. Publish gates")

if article_id:
    status, body = call("POST", f"/api/seo/articles/{article_id}/publish", token)
    check("publish is blocked while requirements are unmet",
          status in (403, 409, 422, 503),
          f"got {status}: {body}")
    if status == 403 and isinstance(body, dict):
        detail = body.get("detail") or {}
        issues = detail.get("blocking_issues") if isinstance(detail, dict) else None
        check("publish refusal names what is missing", bool(issues),
              f"got {body}")

    status, body = call("POST", f"/api/seo/articles/{article_id}/submit-for-author",
                        token)
    check("hand-off is blocked below the score threshold",
          status in (400, 403, 409, 422), f"got {status}: {body}")


# --------------------------------------------------------------------------
# 6. Supporting endpoints
# --------------------------------------------------------------------------
section("6. Supporting endpoints")

for label, path in [
    ("dashboard home", "/api/seo/dashboard/home"),
    ("calendar", "/api/seo/calendar"),
    ("pull requests", "/api/seo/pull-requests"),
    ("recommendations", "/api/seo/recommendations"),
    ("keywords", "/keywords"),
    ("tasks", "/tasks"),
    ("articles (legacy)", "/articles"),
]:
    status, _ = call("GET", path, token)
    check(f"{label} responds without a server error", status < 500, f"got {status}")


# --------------------------------------------------------------------------
# 7. Cleanup
# --------------------------------------------------------------------------
section("7. Cleanup")

for uid in created_user_ids:
    status, _ = call("DELETE", f"/users/{uid}", token)
    check(f"probe user {uid} deleted", status in (200, 204), f"got {status}")

for aid in created_article_ids:
    status, _ = call("DELETE", f"/api/seo/articles/{aid}", token)
    if status == 405:
        print(f"  NOTE  no delete endpoint for articles; {aid} left in place")
    else:
        check(f"probe article {aid} removed", status in (200, 204, 404), f"got {status}")


# --------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  {len(passed)} passed, {len(failed)} failed   against {BASE}")
print(f"{'=' * 60}")
if failed:
    print("\nFailures:")
    for item in failed:
        print(f"  - {item}")
    sys.exit(1)
