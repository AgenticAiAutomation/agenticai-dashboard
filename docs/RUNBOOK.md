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

1. **Review queue** — approve, send back, or reject. Rejected links stop
   counting; sent-back links appear on the associate's Review tab with your note.
2. Glance at **Scoreboard** — targets hit out of 14, streak, average points.

## Raising the level

Raise only when **both** associates have cleared their target five consecutive
working days. Settings → Difficulty level. Tell them before you do it; the target
changing without warning is the fastest way to lose the habit.

| Level | Points | Queries | Avg DA | High-value | Exact anchors | Verified live |
|---|---|---|---|---|---|---|
| 1 Warm-up | 60 | 3 | 20+ | — | < 40% | — |
| 2 Steady | 75 | 4 | 25+ | 1 | < 35% | — |
| 3 Push | 90 | 5 | 30+ | 2 | < 30% | 40% |
| 4 Pro | 110 | 6 | 35+ | 3 | < 25% | 55% |
| 5 Elite | 130 | 7 | 40+ | 4 | < 20% | 70% |

Dropping a level is fine and costs nothing — better than a target nobody meets.

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
