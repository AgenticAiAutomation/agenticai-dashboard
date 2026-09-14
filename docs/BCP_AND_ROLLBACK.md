# Backlink Ops — business continuity and rollback

## The promise

The dashboard keeps serving every pre-existing page — the SEO backlinks tracker,
the article pipeline, the team scoreboard — even if this feature is broken, its
database is gone, or the AI provider is down. Each of those is handled below,
and each is rehearsed by `tests/smoke_app.py` (51 checks).

## Failure modes and what happens

| What breaks | What the team sees | What the system does | Action |
|---|---|---|---|
| Module fails to import | Nothing — dashboard normal, `/seo/backlink-ops` 404 | `register()` catches, logs `failed to mount`, app boots | Read the traceback in the app log, fix, redeploy |
| Route prefix already taken | Feature does not mount | `register()` flattens nested routers, then refuses rather than shadowing an existing route | Change `BACKLINK_OPS_URL_PREFIX` / `_API_PREFIX` |
| Identity adapter does not recognise the session | Desk shows 401 to signed-in users; rest of the dashboard normal | Nothing is written; no auth state is touched | Set `BACKLINK_OPS_USER_HOOK` — see RUNBOOK |
| Wrong framework / unrecognised app object | Feature does not mount | `register()` logs and returns False | Check the import line in `main.py` |
| Feature DB missing | Recreated empty on next request | `init_db()` is idempotent | Restore from `backups/backlink_ops/` — L3 below |
| Feature DB corrupt | `/health` returns 503 | Deploy gate refuses; monitor alerts | L3 restore |
| AI provider down, slow or out of quota | Verdicts and coaching still appear, labelled *offline rules* | `ai.py` falls back to deterministic rules; failure counted in `bo_ai_usage` | Nothing urgent. The desk is fully usable without AI |
| AI daily cap hit | Same as above | Cap enforced before the call | Raise `BACKLINK_OPS_AI_DAILY_CAP` if genuinely needed |
| Bad deploy | Up to ~60s of errors | `deploy.sh` health gate reverts the commit and restarts automatically | Read the log, fix, redeploy |
| Maintenance window | Desk is readable, writes refused with a clear message | `BACKLINK_OPS_READ_ONLY=1` | Flip back to 0 |

## Rollback, three levels

**Always start at L1.** It is instant and loses nothing.

### L1 — turn the feature off · ~10 seconds · zero data loss
```bash
ops/rollback.sh --off
```
Sets `BACKLINK_OPS_ENABLED=0` and restarts. The blueprint is never registered;
the dashboard is byte-for-byte what it was before this feature existed. Every
backlink, keyword and approval stays on disk and returns when you set it back.

**Use L1 whenever you are unsure.** Diagnose afterwards, not during.

### L2 — revert the code · ~30 seconds · zero data loss
```bash
ops/rollback.sh --to pre-backlink-ops-<stamp>     # tag created by preflight.sh
git -C "$APP_DIR" tag | grep pre-backlink-ops     # list available points
```
For when the module is fine but a code change around it is not.

### L3 — restore the feature database · minutes · loses work since the backup
```bash
ls -lt backups/backlink_ops/
ops/rollback.sh --restore backups/backlink_ops/backlink_ops-20260913-0900-nightly.db
```
The file being replaced is copied aside as `.displaced-<epoch>` first — nothing
is deleted. Only for corruption or a destructive mistake.

### Full uninstall
1. `ops/rollback.sh --off`
2. Remove the two lines from `api/app/main.py`
3. Delete `api/app/backlink_ops/`
4. Keep `instance/backlink_ops.db` until you are certain — that is the team's work

Nothing else in the repository was touched, so there is nothing else to undo.
The `seo_backlinks` table and the article pipeline never knew this feature
existed.

## Backups

| What | When | Where | Kept |
|---|---|---|---|
| Feature DB | Nightly cron + before every deploy + on demand from Settings | `backups/backlink_ops/` | 30 newest |
| Host DB + git tag | Before every deploy | `backups/preflight/<stamp>/` | manual prune |

Nightly:
```cron
15 2 * * *  cd /var/www/<app> && /usr/bin/sqlite3 instance/backlink_ops.db \
            ".backup 'backups/backlink_ops/backlink_ops-$(date +\%Y\%m\%d)-nightly.db'"
```
Off-box copy — the VPS is a single point of failure:
```cron
30 2 * * *  rclone copy /var/www/<app>/backups/backlink_ops remote:backups/backlink-ops
```

**A backup you have not restored is not a backup.** Restore into a scratch copy
once a quarter:
```bash
cp backups/backlink_ops/<newest>.db /tmp/verify.db
sqlite3 /tmp/verify.db "PRAGMA integrity_check; SELECT COUNT(*) FROM bo_entries;"
```

## Monitoring

```cron
*/10 * * * *  cd /var/www/<app> && ops/healthcheck.sh >> /var/log/backlink-ops-health.log 2>&1
```
The check fails if the feature is unhealthy **or** a pre-existing dashboard route
is — so it catches collateral damage, not just this module.

Everything this feature logs is prefixed, in the dashboard's own log file:
```bash
journalctl -u <service> | grep backlink-ops | tail -50
```

## Continuity of the work itself

If the whole dashboard is down, the associates are not blocked: they keep
submitting links and running Ubersuggest queries, note them anywhere, and log
them when it is back — the day's date is set server-side from IST on entry, so
ask them to log same-day before midnight IST, or add the entries yourself with
the correct date via a short SQL insert.
