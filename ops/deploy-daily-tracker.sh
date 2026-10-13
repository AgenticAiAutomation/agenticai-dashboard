#!/usr/bin/env bash
# Daily Tracker + per-site levels + /articles removal — dashboard deploy.
# Run as root on the VPS. All three flags stay OFF.
#
#   bash /root/daily-tracker-deploy.sh          (asks before changing anything)
#   bash /root/daily-tracker-deploy.sh --yes    (you've already seen the commit list)
#
# What goes live with the flags off (docs/DAILY_TRACKER.md):
#   * T1  Backlink Ops matches the roster to logins by email or by name
#         ignoring case, and shows a "not live" site to the people rostered on it.
#   * T3  /articles/ redirects home; the page is archived in the repo.
#   * nav + homepage Workspace cards.
# Nothing else changes until daily-tracker-flags.sh switches a flag on.
#
# Order: backups (Postgres, both desk SQLite files, frontend build) → new code
# → restart → checks → frontend build. Any failure before the frontend puts
# the previous code back by itself. Database changes are additive only: one new
# table in backlink_ops.db (old code ignores it) and a new daily_tracker.db.
set -euo pipefail

REPO=/var/www/agenticai-dashboard
BRANCH=feat/daily-tracker-levels
SERVICE=dashboard-api
PUBLIC=https://dashboard.agenticaiautomation.co
STAMP=$(date +%Y%m%d-%H%M%S)
BK=/root/backups/daily-tracker-$STAMP

say()  { printf '\n==> %s\n' "$*"; }
stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || stop "Run this as root."
cd "$REPO"

# ------------------------------------------------------------- checks only
say "Checking the server"
PREV_SHA=$(git rev-parse HEAD)
PREV_BRANCH=$(git symbolic-ref --quiet --short HEAD || true)
echo "    live now: ${PREV_BRANCH:-detached} @ $(git rev-parse --short HEAD)"

DIRTY=$(git status --porcelain --untracked-files=no)
[ -z "$DIRTY" ] || stop "The live code has local edits git doesn't know about:
$DIRTY"

git fetch -q origin "$BRANCH" || stop "Could not fetch $BRANCH from GitHub (has it been pushed?)."
NEW_SHA=$(git rev-parse FETCH_HEAD)
[ "$NEW_SHA" != "$PREV_SHA" ] || stop "Already on $BRANCH @ $(git rev-parse --short HEAD)."
git merge-base --is-ancestor HEAD "$NEW_SHA" || \
  stop "The live code has commits that $BRANCH doesn't contain — deploying would drop them."

[ -x api/venv/bin/python ] || stop "No venv at $REPO/api/venv."
[ -d web/node_modules ] || stop "web/node_modules is missing, so the frontend cannot be built here."
command -v npm >/dev/null || stop "npm not found."
command -v pg_dump >/dev/null || stop "pg_dump not found — no database backup possible."
FREE_MB=$(df -Pm "$REPO" | awk 'NR==2 {print $4}')
[ "$FREE_MB" -ge 1024 ] || stop "Only ${FREE_MB} MB free on the disk; the frontend build needs about 1 GB."
DB_URL=$(grep -E '^DATABASE_URL=' api/.env | head -1 | cut -d= -f2- | tr -d '"'"'" | sed 's/+psycopg2//')
[ -n "$DB_URL" ] || stop "DATABASE_URL not found in api/.env."
git diff --quiet HEAD "$NEW_SHA" -- api/requirements.txt web/package.json web/package-lock.json || \
  stop "Dependencies changed between the live code and $BRANCH — this script does not install them."
git diff --quiet HEAD "$NEW_SHA" -- api/alembic || \
  stop "$BRANCH carries a Postgres migration — this script does not run migrations."

say "These commits will go live"
git log --oneline "HEAD..$NEW_SHA"
echo
echo "    Postgres: no change"
echo "    backlink_ops.db: adds table bo_user_levels (schema 1 → 2), keeps every row"
echo "    daily_tracker.db: created empty on first start"
echo "    flags FEATURE_PER_PROJECT_LEVELS / FEATURE_DAILY_TRACKER / FEATURE_IDEA_BOARD: stay off"
echo "    backups: $BK"
echo
if [ "${1:-}" = --yes ]; then
  echo "Deploy? yes (given as --yes)"
else
  OK=""
  while [ -z "$OK" ]; do
    read -r -p "Deploy? Type yes to continue: " OK || stop "No answer."
    OK=${OK//$'\r'/}
  done
  [ "$OK" = yes ] || stop "Cancelled."
fi

# ------------------------------------------------------------- backups
say "Backups → $BK"
mkdir -p "$BK"
chmod 700 "$BK"
pg_dump "$DB_URL" > "$BK/dashboard_$STAMP.sql" || stop "pg_dump failed."
tar -C "$(dirname "$REPO")" --exclude='agenticai-dashboard/web/node_modules' \
    --exclude='agenticai-dashboard/api/venv' -czf "$BK/code.tgz" "$(basename "$REPO")"
# SQLite's own online backup: safe while the dashboard is running.
for DB in backlink_ops invoice_desk daily_tracker; do
  SRC=$REPO/api/instance/$DB.db
  [ -f "$SRC" ] || continue
  api/venv/bin/python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
    "$SRC" "$BK/$DB.db" || stop "Backup of $DB.db failed."
done
echo "$PREV_SHA ${PREV_BRANCH:-detached}" > "$BK/previous-commit.txt"
echo "    $(ls "$BK" | tr '\n' ' ')"

# ------------------------------------------------------------- rollback
ROLLED=0
rollback() {
  [ "$ROLLED" = 1 ] && return; ROLLED=1
  printf '\n!!! %s — rolling back\n' "$1" >&2
  journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
  if [ -n "$PREV_BRANCH" ]; then git checkout -q -B "$PREV_BRANCH" "$PREV_SHA"; else git checkout -q "$PREV_SHA"; fi
  systemctl restart "$SERVICE"; sleep 6
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    echo "    Rolled back to ${PREV_BRANCH:-detached} @ $(git rev-parse --short HEAD); dashboard healthy." >&2
  else
    echo "    Rolled back but the dashboard is still unhealthy — see docs/BCP_AND_ROLLBACK.md. Backups: $BK" >&2
  fi
  exit 1
}
wait_healthy() {
  for _ in $(seq 1 12); do sleep 5; curl -fsS -o /dev/null "$1" && return 0; done
  return 1
}
route_code() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:5004$1"; }

# ------------------------------------------------------------- deploy
say "Code → $BRANCH @ $(git rev-parse --short "$NEW_SHA")"
git checkout -q -B "$BRANCH" "$NEW_SHA"
install -d -o www-data -g www-data "$REPO/api/instance" "$REPO/api/backups/daily_tracker"

say "Restarting $SERVICE"
systemctl restart "$SERVICE"
wait_healthy http://127.0.0.1:5004/health || rollback "dashboard not healthy after 60s"
BO=$(curl -s http://127.0.0.1:5004/api/seo/backlink-ops/health || true)
echo "$BO" | grep -q '"version": *"1.3.0"' || rollback "Backlink Ops is not on 1.3.0: $BO"
echo "$BO" | grep -q '"schema": *2' || rollback "Backlink Ops database did not reach schema 2: $BO"
echo "$BO" | grep -q '"db_ok": *true' || rollback "Backlink Ops database check failed: $BO"
for _ in $(seq 1 8); do
  CODE=$(route_code /api/seo/articles)
  case "$CODE" in 401|403) ;; *) rollback "article list answered $CODE (wanted 401/403)" ;; esac
  CODE=$(route_code /api/seo/backlink-ops/levels)
  case "$CODE" in 401) ;; *) rollback "levels route answered $CODE on a worker (wanted 401)" ;; esac
  CODE=$(route_code /api/tasks/status)
  case "$CODE" in 404) ;; *) rollback "/api/tasks/status answered $CODE with the flags off (wanted 404)" ;; esac
done
echo "    dashboard healthy · Backlink Ops 1.3.0 schema 2 · tracker not mounted (flags off)"

say "Frontend build (about 1-2 minutes)"
if ! (cd web && npm run build) || [ ! -f web/out/index.html ] || [ ! -f web/out/tasks/index.html ]; then
  printf '\n!!! The frontend build failed. Putting the previous build back.\n' >&2
  rm -rf web/out
  [ -d "$BK" ] && tar -xzf "$BK/code.tgz" -C /tmp "$(basename "$REPO")/web/out" 2>/dev/null \
    && mv "/tmp/$(basename "$REPO")/web/out" web/out
  echo "    The API is on the new code with every flag off, which the old screens work with." >&2
  echo "    Send this output to Claude." >&2
  exit 2
fi

say "Checking from outside"
for P in /dashboard/ /tasks/ /articles/; do
  CODE=000
  for _ in $(seq 1 6); do
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC$P" || true)
    [ "$CODE" = 200 ] && break
    sleep 5
  done
  [ "$CODE" = 200 ] || { printf '\n!!! %s answered %s from outside (wanted 200).\n    Send this output to Claude.\n' "$P" "$CODE" >&2; exit 2; }
done

say "Done — deployed with every flag OFF"
echo "    Backups: $BK"
echo "    Next: bash /root/daily-tracker-flags.sh levels   (then: tracker, ideas)"
