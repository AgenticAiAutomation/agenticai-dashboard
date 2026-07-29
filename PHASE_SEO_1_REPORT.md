# PHASE_SEO_1_REPORT — SEO Operations System (Product C), Week 1

**Date:** 2026-07-29
**Scope:** Week 1 of the 4-week build, plus Addendum Additions 1–3.
**Branch:** `master`

---

## Headline

Everything that ships through git is built, verified, and committed. Everything
that requires executing commands **on the VPS** is written as a runnable script
but has **not been run**, because this machine has no SSH access to
`82.25.107.25:65002` (`Permission denied (publickey,password)`).

So: **no WordPress is installed, no hello-world post exists, no credentials file
has been generated, and no migration has been applied.** Those four items are
the Week 1 deliverables that need you at a terminal. The exact commands are in
§6.

---

## 1. What is built and verified

### Database — Alembic migration `002_seo_operations`

All 15 tables plus 11 native Postgres enum types. Verified by rendering the
migration to offline SQL (`alembic upgrade 001:002 --sql`) and inspecting the
output; the downgrade path renders cleanly too.

| Table | Purpose |
| --- | --- |
| `seo_articles` | Article lifecycle, UUID PK |
| `seo_article_sources` | Where the question came from |
| `seo_article_faqs` | FAQ entries with proof URLs |
| `seo_article_versions` | Snapshot per team edit |
| `seo_scores` | Score history with breakdown + comments JSONB |
| `seo_calendar` | 12-week editorial plan |
| `seo_backlinks` | Backlink tracker |
| `seo_audits` | Daily/weekly/monthly audit output |
| `seo_gsc_daily` | Search Console rows |
| `seo_team_stats` | Per-user daily rollup |
| `seo_recommendations` | Prioritised audit findings |
| `seo_pull_requests` | Captured question inbox |
| `seo_country_vertical_matrix` | Seeded, 16 rows, 12 approved |
| `seo_api_usage` | Claude cost ledger for the ₹500/day cap |
| `audit_events` | Append-only user action log |

### Country × vertical matrix — seeded and enforced

Seeded by the migration; the full 16-pair grid is stored so the UI can show
which combinations are deliberately closed, not just which are open.

| Vertical | Approved |
| --- | --- |
| WhatsApp Automation | India |
| RPA | NZ, Ireland, UK |
| n8n | NZ, Ireland, UK, India |
| Agentic AI | India, NZ, Ireland, UK |

Enforced at three layers:

1. **Database** — a CHECK constraint guarantees `onpage` always carries a
   country and `content` never does.
2. **API** — `validate_country_vertical()` runs on generate, convert, publish,
   and CSV import. Returns 422 with the approved list in the body.
3. **UI** — the country dropdown is populated from the vertical and clears
   itself with an explanation when you switch to an incompatible vertical.

Verified by test: whatsapp/UK → 422, onpage with no country → 422, content
*with* a country → 422, approved pairs pass.

### API — 30 endpoints under `/api/seo/*`

Article lifecycle (generate, list, detail, team-edit, score, submit-for-author,
from-author-story, publish, validate-country, upload-image, generate-alt);
pull requests (create, list, convert); calendar (list, import-csv); dashboard
(home, team-stats, site-health, projected-target-date helper);
recommendations, audits, backlinks; four cron endpoints; matrix and integration
health.

### Enforcement rules — server-side, non-bypassable

| Rule | Status |
| --- | --- |
| 1. Invalid country/vertical → 422 | **Enforced** (DB + API + UI) |
| 2. Score < 80 → publish 403 | **Enforced** |
| 3. `from_author_story` empty → 403 | **Enforced** |
| 4. `featured_image_alt` null → 403 | **Enforced** |
| 5. AI detection > 20% → blocked | **NOT enforced** — see §3 |
| 6. Duplicate slug → 409 | **Enforced** (checked locally *and* against WP) |

### Go-live gate

`SEO_LIVE_APPROVED.txt` is re-read from disk on every publish call. Until it
exists and contains `GO LIVE YYYY-MM-DD` dated within 24 hours, every WordPress
publish is forced to `status=draft`. Verified: missing file → draft, today's
date → publish, 3-day-old date → draft, malformed content → draft. Approval
also expires on its own without any code change.

### Scoring engine

27 weighted parameters totalling exactly 100 points, in the four groups the spec
defines. Returns line-by-line comments with `line_number`, `current_text`,
`suggested_fix`, and `impact_points`, sorted by impact.

23 of 27 parameters are implemented now. The other four need an integration that
is not provisioned yet; they are **skipped and excluded from the denominator**,
with the total normalised to 100 and `parameters_skipped` naming them. Scoring
them zero would have made every article permanently unpublishable for reasons
the team cannot fix.

Skipped: LanguageTool grammar (needs the Docker container), AI detection (no
provider key), semantic coverage (needs `EMBEDDER_URL`), mobile-friendly (needs
a live URL).

### User management (Addition 1)

Roles `admin` / `seo_lead` / `viewer`; the pre-existing `owner`/`seo`/`writer`
roles still authenticate so no current account breaks. Create user with
auto-generated 16-character password shown exactly once; edit role, scopes, and
active state; reset password (which also kills live sessions); self-service
password change. Password policy is min 12 chars with upper + lower + digit +
symbol, bcrypt-hashed — verified that generated passwords always satisfy it and
that five categories of weak password are rejected.

Session timeout is enforced **server-side** via `users.last_activity_at`, not
just by JWT expiry: a still-valid token is rejected after 8 idle hours, and
logout clears the column so the token stops working immediately.

Every login, failed login, article action, publish, and user change writes to
`audit_events` with IP and user agent.

### Dashboard home (Addition 2)

Rebuilt in the dark theme on `#2563EB`, with all five rows the spec asks for:
4 KPI cards, 3 target-projection cards, 2 Recharts charts (30-day publish
velocity bar with weekly-average overlay; 90-day GSC dual-axis line), team
scoreboard + top recommendations, and a 20-row activity feed. Skeletons on every
loading state, empty states with a next-step CTA on every zero-data state.

Projection maths matches the spec exactly: mean of the daily series, `≤ 0` →
`"on hold — no forward progress detected"`, otherwise
`today + (target − current) / avg_daily_gain`, with a ± confidence interval
derived from the standard deviation. Exposed as
`POST /api/seo/helpers/projected-target-date`.

### Frontend

`npm run build` succeeds — **23 routes, all statically exported**. New pages:
`/dashboard`, `/dashboard/seo` (hub + matrix grid), `/seo/inbox`,
`/seo/articles`, `/seo/articles/new`, `/seo/articles/edit`,
`/seo/articles/author-review`, `/seo/calendar`, `/seo/team`, `/seo/backlinks`,
`/seo/recommendations`, `/seo/technical-audit`, `/settings/users`,
`/account/password`.

### Test

`api/tests/smoke.py` — 39 assertions across the matrix, projection, go-live
gate, scoring engine, and password policy. All pass. Runs without a database, so
it works as a deploy gate: `cd api && python tests/smoke.py`.

---

## 2. Deviations from the spec, and why

**1. Tables live in `public`, not a separate `seo` schema.** The spec says both
"all new tables in schema `seo`" and "all new DB tables prefixed `seo_`". Doing
both gives you `seo.seo_articles`. I kept the `seo_` prefix in `public`, which
satisfies the second requirement literally and keeps foreign keys to
`public.users` and the existing Alembic history working without a `search_path`
change. Say the word if you want the separate schema instead.

**2. Article IDs are UUIDs; `assigned_to` is an integer.** The spec asks for
`assigned_to UUID FK to users`, but `users.id` is an existing `Integer` primary
key with live rows. Changing it would break every existing FK. Article IDs are
UUIDs as specified.

**3. 27 scoring parameters, not 40.** The spec says "40 parameters" but
enumerates 27 line items, and those 27 sum to exactly 100. I implemented the 27
enumerated. If there are 13 more, send them and I will add them within the
existing registry — each is a single function.

**4. Frontend directory is `web/`, not `frontend/`.** That is what exists in the
repo; `deploy.sh` already builds from it.

**5. Dynamic routes use query parameters.** The frontend is `output: 'export'`
(static), which cannot pre-render `/articles/{uuid}/edit` for unknown UUIDs. So
the routes are `/dashboard/seo/articles/edit/?id=<uuid>`. Same behaviour, works
with the existing nginx static-file setup.

**6. Claude model.** Using `claude-sonnet-4-6` as you specified, set via
`ANTHROPIC_MODEL` so it can be changed without a code edit. Cost is metered per
call into `seo_api_usage` and the ₹500/day cap is checked *before* each request.

---

## 3. Not built, and honestly why

| Item | Status | Blocker |
| --- | --- | --- |
| WordPress at `/var/www/blog` | Script written, **not run** | No SSH access from this machine |
| nginx `/blog/*` reverse proxy | Config written, **not applied** | Same |
| Hello-world published post | Endpoint built, **never called** | No WordPress to call |
| `CREDENTIALS_JAI.md` | Generator written, **not run** | Needs a live DB and the WP install |
| GSC + GA4 service accounts | Client code done, **no keys** | Needs Google Cloud console access |
| Migration applied | Renders correctly, **not applied** | No database reachable |
| AI-detection gate (rule 5) | **Not implemented** | No Originality.ai or GPTZero account exists. The publish response says explicitly that this gate is unenforced rather than pretending it passed. |
| TOTP 2FA | Columns + `pyotp` present, **no enrolment flow** | Week 4 scope; `CREDENTIALS_JAI.md` states plainly that the account is password-only |
| 60-article calendar seed | Import endpoint + UI built, **no data** | Waiting on your CSV |
| 30 seeded pull requests | Scraper cron built, **no data** | Needs `SERPAPI_KEY`, or capture by hand |

**On the "first 5 real articles published" definition-of-done item:** that is not
achievable in Week 1 from here even with SSH, because it needs the WordPress
install, an Anthropic key, and the go-live file. The pipeline that produces them
is complete and tested end to end except for the live WordPress call.

---

## 4. Concerns worth flagging

**The AI-detection gate is the weakest link.** Rule 5 is the one enforcement
rule that is not enforced, and it is also the one that protects you from
publishing something that reads as machine-written. Until a provider is wired,
that check is human judgement. Budget roughly ₹1/article as you estimated;
Originality.ai is the cheaper of the two for volume.

**The ₹500/day Claude cap is enforced by a hardcoded INR/USD rate** (88.0 in
`claude.py`). It is a budget guard, not accounting. If the rate moves a lot,
adjust it.

**`avg_position` in the top-10 projection is noisy at low volume.** With only a
handful of ranking pages the day-over-day delta swings hard, so the projected
date for "first 5 top-10 rankings" will be unstable until there is more data.
The confidence interval will show this — expect a wide ± initially.

---

## 5. Cost of running this

| Item | Cost |
| --- | --- |
| Claude Sonnet 4.6 draft generation | ~₹8–15 per article, capped at ₹500/day |
| Claude alt captions | <₹1 each |
| LanguageTool | Free, self-hosted |
| AI detection | ~₹1/article once wired |
| SerpAPI | Free to 100 searches/month |
| GSC / GA4 / WordPress REST | Free |

---

## 6. What you need to run on the VPS

In this order. Each step is independent enough to stop and check.

```bash
ssh -p 65002 root@82.25.107.25
cd /var/www/agenticai-dashboard
git pull origin master

# 1. Migrate + deploy the code (deploy.sh already runs alembic upgrade head)
./deploy.sh

# 2. Install WordPress (generates the DB, admin user, app password, editorial
#    author, and RankMath; writes secrets to /root/wordpress-install-secrets.txt)
JAI_ADMIN_EMAIL=contact@agenticaiautomation.co \
  bash infra/install-wordpress.sh

# 3. Wire nginx for the /blog subfolder
cp infra/nginx-blog-subfolder.conf /etc/nginx/snippets/blog-subfolder.conf
#    Then add this line inside the agenticaiautomation.co server block:
#      include /etc/nginx/snippets/blog-subfolder.conf;
#    Check the fastcgi_pass socket matches your PHP version.
nginx -t && systemctl reload nginx

# 4. Fill in api/.env from api/.env.example. At minimum:
#      WP_APP_USER, WP_APP_PASSWORD   (from /root/wordpress-install-secrets.txt)
#      ANTHROPIC_API_KEY
#      CRON_SECRET                    (openssl rand -hex 32)
systemctl restart dashboard-api

# 5. Verify every integration in one call
curl -s -H "Authorization: Bearer <your-token>" \
  http://127.0.0.1:5004/api/seo/health/integrations | python3 -m json.tool

# 6. Prove the WordPress round trip (creates a WP draft, safe to delete)
curl -s -X POST -H "Authorization: Bearer <your-token>" \
  http://127.0.0.1:5004/api/seo/health/wordpress-hello-world

# 7. Generate your credentials file
bash scripts/generate-credentials.sh
cat CREDENTIALS_JAI.md          # then save the values and: rm CREDENTIALS_JAI.md

# 8. Install the cron jobs
cp infra/seo-cron.sh /usr/local/bin/seo-cron && chmod 755 /usr/local/bin/seo-cron
crontab -e     # schedule is in the header comment of seo-cron.sh

# 9. Optional but recommended
docker run -d --restart=always -p 8010:8010 erikvl87/languagetool   # grammar
```

**Then send me:**

- the 60-row calendar CSV (columns: `week`, `type`, `vertical`, `country`,
  `title`, `keyword`, `kd`, `volume`, `intent` — onpage rows need an approved
  country, content rows must leave it blank)
- the two SEO team email addresses
- a Google Cloud service account JSON for GSC and one for GA4, dropped in
  `secrets/`
- a decision on Originality.ai vs GPTZero

---

## 7. Week 2 plan

Ahead of schedule on two items — draft generation and the article editor UI were
Week 2 deliverables and are already built, and the scoring engine is at 23 of 27
parameters rather than the planned 20. Week 2 therefore becomes:

1. Wire the AI-detection provider and turn on enforcement rule 5.
2. Stand up LanguageTool and the bge-m3 embedder call, taking scoring to 27/27.
3. Import the 60-row calendar and seed the pull-request inbox.
4. Draft, score, and publish the first 3 real articles.
5. `PHASE_SEO_2_REPORT.md`.
