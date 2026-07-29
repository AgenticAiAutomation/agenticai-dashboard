"""Smoke test for the enforcement logic that needs no database.

Covers the country x vertical matrix (enforcement rule 1), the target-reach
projection helper, the go-live gate, the scoring engine, and the password
policy.

Run from the api/ directory:
    python tests/smoke.py

Exits non-zero on any failure, so it works as a deploy gate.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

os.environ.update({
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "JWT_SECRET_KEY": "x", "INITIAL_OWNER_EMAIL": "a@b.co",
    "INITIAL_OWNER_PASSWORD": "x", "CORS_ORIGINS": "http://localhost",
})
sys.path.insert(0, os.path.abspath("."))

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    if not condition:
        failures.append(name)


# ---------------------------------------------------------------- matrix
from app.seo.matrix import APPROVED_MATRIX, seed_rows, validate_country_vertical
from app.seo.enums import ArticleType, Country, Vertical
from fastapi import HTTPException

rows = seed_rows()
approved = [r for r in rows if r["approved"]]
check("matrix seeds 16 pairs", len(rows) == 16, f"{len(rows)}")
check("matrix approves 12 pairs", len(approved) == 12, f"{len(approved)}")
check("whatsapp is India-only", APPROVED_MATRIX[Vertical.whatsapp] == [Country.india])
check("rpa excludes India", Country.india not in APPROVED_MATRIX[Vertical.rpa])


class FakeQuery:
    def filter(self, *a, **k): return self
    def all(self): return []          # forces the code fallback path


class FakeDb:
    def query(self, *a, **k): return FakeQuery()


db = FakeDb()

# Rule 1: onpage + unapproved pair -> 422
try:
    validate_country_vertical(db, ArticleType.onpage, Vertical.whatsapp, Country.uk)
    check("rule 1 rejects whatsapp/UK", False)
except HTTPException as e:
    check("rule 1 rejects whatsapp/UK", e.status_code == 422,
          e.detail.get("error"))

# Rule 1: onpage with no country -> 422
try:
    validate_country_vertical(db, ArticleType.onpage, Vertical.rpa, None)
    check("rule 1 rejects onpage with no country", False)
except HTTPException as e:
    check("rule 1 rejects onpage with no country", e.status_code == 422,
          e.detail.get("error"))

# Rule 1: content with a country -> 422
try:
    validate_country_vertical(db, ArticleType.content, Vertical.rpa, Country.uk)
    check("rule 1 rejects content with a country", False)
except HTTPException as e:
    check("rule 1 rejects content with a country", e.status_code == 422,
          e.detail.get("error"))

# Approved pairs pass
try:
    validate_country_vertical(db, ArticleType.onpage, Vertical.rpa, Country.nz)
    validate_country_vertical(db, ArticleType.content, Vertical.n8n, None)
    check("approved pairs pass", True)
except HTTPException as e:
    check("approved pairs pass", False, str(e.detail))

# ------------------------------------------------------------ projection
from app.seo.services.projection import daily_deltas, project_target_date

p = project_target_date("DR 25", current_value=10, target_value=25,
                        historical_daily_progress=[0.5] * 14,
                        today=date(2026, 7, 29))
check("projection computes a date", p.projected_date == date(2026, 8, 28),
      str(p.projected_date))
check("projection reports velocity", p.avg_daily_gain == 0.5)

stalled = project_target_date("DR 25", 10, 25, [0, 0, 0, -1])
check("zero velocity is on hold", stalled.status == "on_hold", stalled.message)
check("on-hold message matches spec",
      stalled.message == "on hold — no forward progress detected")

achieved = project_target_date("done", 30, 25, [1, 1])
check("met target reports achieved", achieved.status == "achieved")

slipping = project_target_date("60 articles", 10, 60, [0.5] * 14,
                               deadline=date(2026, 8, 1), today=date(2026, 7, 29))
check("past-deadline projection flags risk",
      slipping.status in ("slipping", "at_risk"), slipping.status)
check("confidence interval present", slipping.confidence_days is not None)
check("daily_deltas differences", daily_deltas([1, 3, 6]) == [2, 3])

# --------------------------------------------------------------- go-live
from app.seo.golive import check_go_live

with tempfile.TemporaryDirectory() as tmp:
    missing = os.path.join(tmp, "nope.txt")
    check("missing approval file blocks live", not check_go_live(missing).approved)
    check("blocked publishes go to draft", check_go_live(missing).wp_status == "draft")

    today_file = os.path.join(tmp, "ok.txt")
    with open(today_file, "w") as fh:
        fh.write(f"GO LIVE {date.today().isoformat()}\n")
    status = check_go_live(today_file)
    check("today's approval unlocks live", status.approved, status.reason)
    check("approved publishes go live", status.wp_status == "publish")

    stale_file = os.path.join(tmp, "stale.txt")
    with open(stale_file, "w") as fh:
        fh.write(f"GO LIVE {(date.today() - timedelta(days=3)).isoformat()}\n")
    check("stale approval expires", not check_go_live(stale_file).approved)

    bad_file = os.path.join(tmp, "bad.txt")
    with open(bad_file, "w") as fh:
        fh.write("please publish everything\n")
    check("malformed approval blocks live", not check_go_live(bad_file).approved)

# --------------------------------------------------------------- scoring
from app.seo.services.scoring import REGISTRY, ScoringContext, score_article

total_points = sum(p.points_available for p in REGISTRY)
check("registry sums to 100 points", total_points == 100, str(total_points))

markdown = """# WhatsApp automation for Indian retailers

WhatsApp automation cuts response time. Teams in India rely on it daily.
It saves hours. Retailers see fewer dropped conversations.

## Why manual replies break down

Support teams answer the same questions repeatedly. That work does not scale.
A person can hold maybe six threads. A queue holds thousands.

### The cost of delay

Every minute of delay loses a sale. Buyers move on quickly.

## Building the workflow

Start with the catalogue. Map each intent to a reply template.
See [our n8n guide](/blog/n8n-guide) and [the RPA primer](/blog/rpa-primer).
The [official docs](https://developers.facebook.com/docs/whatsapp) explain limits,
and [Meta's policy](https://www.whatsapp.com/legal) covers messaging rules.

[FROM AUTHOR: 200 words on real production story about WhatsApp automation]
"""

ctx = ScoringContext(
    markdown=markdown, lines=markdown.splitlines(),
    primary_keyword="WhatsApp automation",
    title="WhatsApp automation for Indian retailers",
    slug="whatsapp-automation-indian-retailers",
    meta_description="A" * 150,
    from_author_story=None,
    featured_image_alt=None,
    faqs=[{"question": f"Q{i}", "answer": "word " * 50, "source_url": "https://x.co"}
          for i in range(5)],
    inbound_internal_links=2,
)
report = score_article(ctx)

check("scoring returns a 0-100 total", 0 <= report["total_score"] <= 100,
      str(report["total_score"]))
check("skipped params are excluded, not zeroed",
      report["raw_available"] < 100, f"available={report['raw_available']}")
check("comments carry the spec fields",
      all({"line_number", "current_text", "suggested_fix", "impact_points"}
          <= set(c) for c in report["comments"]))
check("missing From Author is flagged",
      any(c["parameter"] == "from_author" for c in report["comments"]))
check("missing alt caption is flagged",
      any(c["parameter"] == "image_alt" for c in report["comments"]))
check("keyword placement detected",
      next(p for p in report["parameters"]
           if p["key"] == "keyword_placement")["points_earned"] > 0)
check("internal links counted",
      next(p for p in report["parameters"]
           if p["key"] == "internal_links")["points_earned"] == 3)
check("external links counted",
      next(p for p in report["parameters"]
           if p["key"] == "external_links")["points_earned"] == 3)
check("heading hierarchy scored",
      next(p for p in report["parameters"]
           if p["key"] == "heading_hierarchy")["points_earned"] > 0)
check("word count under target is penalised",
      next(p for p in report["parameters"]
           if p["key"] == "word_count")["points_earned"] < 5)

print(f"\nscore={report['total_score']}/100  "
      f"(raw {report['raw_earned']}/{report['raw_available']})")
print(f"skipped: {', '.join(report['parameters_skipped'])}")
print(f"comments: {len(report['comments'])}")

# ------------------------------------------------------- password policy
from app.auth import generate_password, validate_password_policy

for _ in range(50):
    validate_password_policy(generate_password(16))
check("generated passwords always satisfy policy", True)

for weak in ["short1!A", "alllowercase1!", "NOLOWERCASE1!", "NoDigits!!!!!", "NoSymbol123AB"]:
    try:
        validate_password_policy(weak)
        check(f"policy rejects {weak!r}", False)
    except HTTPException:
        check(f"policy rejects {weak!r}", True)

print("\n" + "=" * 60)
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
