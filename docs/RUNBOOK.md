# Backlink Ops — runbook

Day-to-day operation. For failures, see `BCP_AND_ROLLBACK.md`.

## Daily, the associate

1. Open `https://dashboard.agenticaiautomation.co/seo/backlink-ops` (already
   signed in to the dashboard).
2. **Today** — log each submitted link as you submit it, not in a batch at the
   end. The points update live and the requirement list shows what is left.
3. **Keyword Lab** — run the one query shown, paste the result, read the verdict,
   use the suggested anchors. Repeat until the day's query count is met.
4. Clear every requirement → confetti. That is the task complete, not "I logged
   some links".

## Daily, Jai

1. **Review queue** — since v1.1 the automatic review (below) has already
   approved the clear passes and bounced the clear failures. What is left is
   marked *Needs a human look* with the reason. Approve, send back, or reject.
2. Glance at **Scoreboard** — targets hit out of 14, streak, average points.

## Automatic review (v1.1)

The desk was designed so the superuser approves every link. At 30-40 links per
associate per day that is a full-time job, so the first pass is automatic:

1. Every pending link is **opened** and checked for a link to our domain — the
   anchor text and the real `rel` attribute come from the page, not the form.
   If the form said dofollow and the page says nofollow, the entry is corrected
   and still approved (the note says so).
2. **Hard rules**, no judgement needed, sent back with a one-line reason: page
   404/410; page opened but our link is not on it; spam score over 5%; a third
   link on the same site that day.
3. Everything that passed goes to the AI in **one batched call** per run, which
   judges relevance, whether the claimed DA is plausible for that domain, and
   spam sites. `approve` / `needs_fix` (with a note to the associate) / `flag`
   (only when it genuinely cannot tell). With the AI off, capped or down the
   rules decide alone: a verified link is approved, an unverifiable one is
   flagged for you — nothing is ever silently dropped.

Sites that wall off bots or render links with JavaScript (Reddit, Quora,
LinkedIn, Medium…) cannot be verified; the AI is told so and, without AI, they
are flagged rather than bounced.

Runs from cron once an hour, 9 AM–8 PM IST (12 runs a day, so at most 12 AI
calls a day from this feature), or from **Difficulty & team → Run now**. Every
decision is recorded in `bo_reviews` with reviewer `auto` or `ai`, and in the
audit trail, with the reason — a human can always see why.

```
# ops/backlink-ops.env and the systemd unit, same value in both
BACKLINK_OPS_AUTOREVIEW=1
BACKLINK_OPS_CRON_SECRET=<openssl rand -hex 24>

# root crontab (server clock is UTC; 03:30–14:30 UTC = 09:00–20:00 IST)
30 3-14 * * *  cd /var/www/agenticai-dashboard && ops/auto-review.sh >> /var/log/backlink-ops-autoreview.log 2>&1
```

Turn it off without a deploy: `BACKLINK_OPS_AUTOREVIEW=0` and restart — links
then wait for you as in v1.0.

## Raising the level

Raise only when **both** associates have cleared their target five consecutive
working days. Settings → Difficulty level. Tell them before you do it; the target
changing without warning is the fastest way to lose the habit.

v1.1 recalibrated the ladder for a team that logs 30-40 links a day each (the
v1.0 60-point day was 4-10 links and measured nothing) and added a **links
floor** — approved-or-pending links per associate per day — beside the points
target. The numbers are editable per level under **Difficulty & team → Level
targets** (points, links, queries, average DA, high-value); the table below is
the shipped default, and *Back to defaults* restores it.

| Level | Points | Links | Queries | Avg DA | High-value | Exact anchors | Verified live |
|---|---|---|---|---|---|---|---|
| 1 Warm-up | 250 | 40 | 3 | 20+ | — | < 40% | — |
| 2 Steady | 300 | 45 | 4 | 25+ | 1 | < 35% | — |
| 3 Push | 350 | 50 | 5 | 30+ | 2 | < 30% | 40% |
| 4 Pro | 420 | 55 | 6 | 35+ | 3 | < 25% | 55% |
| 5 Elite | 500 | 60 | 7 | 40+ | 4 | < 20% | 70% |

The points targets are first estimates for that volume; watch a week of real
scores and adjust from the desk rather than the code.

Dropping a level is fine and costs nothing — better than a target nobody meets.

## Adding a website

**Difficulty & team → Websites → Add website.** Id (short, no spaces), domain,
name, the page paths links may point to, one line on what the business is (the
AI reads it), seed keywords for the Keyword Lab, and the *Live* tick. A site
that is not ticked is hidden from associates — prepare it, then flip it on the
day it launches. Seed sites (AgenticAI, DIYMart, WhatsAppAutomation) can be
edited but not removed. Nothing here needs a deploy; it lives in `bo_config`.

`whatsappautomation.co.in` ships in the list, **not live**, with `/` as its
only page: the domain was still parked in Sept 2026. When the site is up, fill
in its real paths and tick Live.

## Adding or changing an associate

Settings → Team & assignments. Name must match how the dashboard shows them, or
their project will not preload. Removing someone does **not** delete their logged
work; history and scoreboard keep them.

## Making someone superuser

Not in the UI, on purpose. Add their email to `BACKLINK_OPS_SUPERUSERS` in the
`dashboard-api` environment file and restart. Role escalation should require
server access.

## Roles, and where they come from

The desk creates no users and changes nothing in the dashboard's users table.
It reads the role that is already on the account and maps it:

| Dashboard role | Desk role | Set by |
|---|---|---|
| Jai's email, any role | superuser | `BACKLINK_OPS_SUPERUSERS` |
| `admin`, `seo_lead` | admin | `BACKLINK_OPS_ADMIN_ROLES` |
| `viewer` | viewer (read-only) | `BACKLINK_OPS_VIEWER_ROLES` |
| authenticated, unrecognised role | viewer | safe default |

To give a new associate the desk, give them `seo_lead` in the dashboard as
usual. Nothing else.

## If the desk shows 401 to someone who is signed in

The identity adapter did not recognise the dashboard's session. Fix it with the
hook rather than by changing the auth system:

```
BACKLINK_OPS_USER_HOOK=api.app.deps:get_current_user_optional
```
It receives the request and returns the user (dict, pydantic model or ORM row —
`email`, `name`, `role`/`roles` are read), or `None` when nobody is signed in.
**It must not raise.** If the existing dependency raises 401, wrap it in a new
file rather than editing it — see WORKORDER.md Phase 2 Step 3.

Check what the desk sees:
```bash
curl -s https://api.dashboard.agenticaiautomation.co/api/seo/backlink-ops/bootstrap \
     -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['me'])"
```

## If the API works but the page itself shows nobody signed in

The hook above covers API calls that carry the dashboard's token. The desk
*page* is plain HTML and, by default, calls the API with the browser's cookies
(`credentials: "same-origin"`). A dashboard that keeps its JWT in
`localStorage` and sends it as an `Authorization: Bearer` header from
JavaScript — this one does, see `web/lib/api.ts` — never sets a cookie, so the
page has nothing to send and everyone looks anonymous.

Token mode fixes that without touching the auth system:

```
BACKLINK_OPS_TOKEN_STORAGE_KEY=access_token   # the frontend's localStorage key
BACKLINK_OPS_LOGIN_URL=/login/                # where a 401 sends the browser
```

Two conditions: the page must be served **same-origin** with the frontend
(localStorage is per-origin), and the frontend's login must land the token
under that key. On this host nginx proxies `/seo/backlink-ops` and
`/api/seo/backlink-ops` from `dashboard.agenticaiautomation.co` to the API
for exactly that reason — `sites-available/dashboard-frontend`. With both
blank the page behaves as shipped (cookie mode, reload on 401).

## Turning the AI layer on

In-house default is **Grok** — free tier, and this desk makes roughly 20 calls a
day, which is noise for any provider.

```
BACKLINK_OPS_AI_PROVIDER=grok            # grok | gemini | anthropic | none
BACKLINK_OPS_AI_MODEL=grok-3-mini        # confirm the current id at docs.x.ai/docs/models
BACKLINK_OPS_AI_KEY=xai-...
BACKLINK_OPS_AI_DAILY_CAP=200
```

Restart, then **run the self-test** — this is not optional when you change
provider or model:

```bash
curl -s -X POST https://api.dashboard.agenticaiautomation.co/api/seo/backlink-ops/ai-selftest      -b cookies.txt | python3 -m json.tool
```

`{"ok": true}` means live calls return parseable JSON. Anything else names the
problem — bad key, wrong model id, a reply with no JSON in it.

**Why the self-test matters:** a broken provider is invisible in normal use. The
module catches the failure and falls back to deterministic rules, so the desk
keeps working and nobody reports a bug — you would simply be getting canned
advice while believing it came from a model. The UI labels those answers
*offline rules*; if every verdict says that, the provider is down.

Switching back costs nothing: `BACKLINK_OPS_AI_PROVIDER=none`, restart.

## Maintenance window

```bash
# freeze writes, keep the desk readable
sudo sed -i 's/^BACKLINK_OPS_READ_ONLY=.*/BACKLINK_OPS_READ_ONLY=1/' /etc/default/<service>
sudo systemctl restart <service>
# ... do the work ...
sudo sed -i 's/^BACKLINK_OPS_READ_ONLY=.*/BACKLINK_OPS_READ_ONLY=0/' /etc/default/<service>
sudo systemctl restart <service>
```

## Checking what happened

```bash
journalctl -u <service> | grep backlink-ops | tail -50     # host log, prefixed
curl -s .../api/seo/backlink-ops/audit -b cookies.txt      # audit trail, superuser
sqlite3 instance/backlink_ops.db \
  "SELECT at, actor, action, target FROM bo_audit ORDER BY id DESC LIMIT 20;"
```

## Exporting the month

```bash
sqlite3 -header -csv instance/backlink_ops.db \
  "SELECT e.date, e.author, e.project, e.url, e.type, e.da, e.anchor, e.target,
          COALESCE(r.status,'pending') status
   FROM bo_entries e LEFT JOIN bo_reviews r ON r.entry_id = e.id
   WHERE e.date >= date('now','start of month') ORDER BY e.date;" > backlinks.csv
```

## Giving the page the dashboard's chrome

The page is a standalone HTML document with two placeholders and no template
engine, so it cannot inherit a broken layout and adds no Jinja dependency.

To put it inside the dashboard's own shell instead, the cheap option is an
iframe on an existing dashboard page pointing at `/seo/backlink-ops/`. The
thorough option is to move the markup into the dashboard's front end and keep
calling the same API — every endpoint in `docs/API.md` works unchanged, because
the server holds all the logic.

Either way, do it as its own commit after the feature is proven standalone.

## Relationship to the existing backlinks tracker

The dashboard's `seo_backlinks` table and `/api/seo/backlinks*` routes are
untouched and still live. Two trackers is deliberate for now:

- The old one stays as-is so nothing in flight breaks.
- The new desk is where the daily target, review queue and scoreboard live.

**Tell the associates which one is the live one** — that is the only real risk
here. If you later want one place, that is a separate piece of work: a one-time
importer into `bo_entries`, then retire the old page. Do not hand-merge the
tables.
