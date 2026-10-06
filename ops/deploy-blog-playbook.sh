#!/usr/bin/env bash
# Blog Playbook — dashboard deploy, run as root on the VPS. Flag stays OFF.
#
#   bash /root/blog-playbook-deploy.sh          (asks before changing anything)
#   bash /root/blog-playbook-deploy.sh --yes    (you've already seen the commit list)
#
# Order (docs/BLOG_PLAYBOOK.md): backup → score snapshot with the OLD code →
# new code → migration → restart → score snapshot with the NEW code, which must
# match to the decimal → frontend build. Any failure before the frontend puts
# the previous code and database revision back by itself. A frontend build
# failure restores the previous build and leaves the (compatible) API running.
#
# Needs /root/playbook_score_parity.py (copied there with this script).
set -euo pipefail

REPO=/var/www/agenticai-dashboard
BRANCH=feat/blog-playbook
SERVICE=dashboard-api
PARITY_COPY=/root/playbook_score_parity.py
PUBLIC=https://dashboard.agenticaiautomation.co
STAMP=$(date +%Y%m%d-%H%M%S)
BK=/root/backups/blog-playbook-$STAMP

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

git fetch -q origin "$BRANCH"
NEW_SHA=$(git rev-parse FETCH_HEAD)
[ "$NEW_SHA" != "$PREV_SHA" ] || stop "Already on $BRANCH @ $(git rev-parse --short HEAD)."
git merge-base --is-ancestor HEAD "$NEW_SHA" || \
  stop "The live code has commits that $BRANCH doesn't contain — deploying would drop them."

[ -x api/venv/bin/python ] || stop "No venv at $REPO/api/venv."
[ -x api/venv/bin/alembic ] || stop "No alembic in $REPO/api/venv."
[ -f "$PARITY_COPY" ] || stop "$PARITY_COPY is missing — copy it from api/scripts first."
[ -d web/node_modules ] || stop "web/node_modules is missing, so the frontend cannot be built here."
command -v npm >/dev/null || stop "npm not found."
command -v pg_dump >/dev/null || stop "pg_dump not found — no database backup possible."

FREE_MB=$(df -Pm "$REPO" | awk 'NR==2 {print $4}')
[ "$FREE_MB" -ge 1024 ] || stop "Only ${FREE_MB} MB free on the disk; the frontend build needs about 1 GB."

DB_URL=$(grep -E '^DATABASE_URL=' api/.env | head -1 | cut -d= -f2- | tr -d '"'"'" | sed 's/+psycopg2//')
[ -n "$DB_URL" ] || stop "DATABASE_URL not found in api/.env."

REV=$(cd api && venv/bin/alembic current 2>/dev/null | tail -1 || true)
case "$REV" in
  002*) MIGRATE=1 ;;
  003_playbook_blocks*) MIGRATE=0 ;;
  *) stop "Database revision is '${REV:-unknown}', expected 002. Send this output to Claude." ;;
esac

if git diff --quiet HEAD "$NEW_SHA" -- api/requirements.txt web/package.json web/package-lock.json; then
  DEPS="none"
else
  stop "Dependencies changed between the live code and $BRANCH — this script does not install them."
fi

say "These commits will go live"
git log --oneline "HEAD..$NEW_SHA"
echo
echo "    database: $([ "$MIGRATE" = 1 ] && echo 'add nullable column seo_articles.playbook_blocks (002 → 003_playbook_blocks)' || echo 'already at 003_playbook_blocks')"
echo "    new packages: $DEPS"
echo "    flag BLOG_PLAYBOOK_ENABLED: stays off (nobody sees a change)"
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
pg_dump "$DB_URL" > "$BK/postgres.sql" || stop "pg_dump failed."
[ -d web/out ] && tar -C web -czf "$BK/web-out.tgz" out
echo "$PREV_SHA ${PREV_BRANCH:-detached}" > "$BK/previous-commit.txt"
echo "    database $(du -h "$BK/postgres.sql" | cut -f1), frontend build saved"

say "Score snapshot with the code that is live now"
(cd api && venv/bin/python "$PARITY_COPY" --out "$BK/parity-before.json") || \
  stop "The scoring snapshot failed with the live code."

# ------------------------------------------------------------- rollback
ROLLED=0
MIGRATED=0
rollback() {
  [ "$ROLLED" = 1 ] && return; ROLLED=1
  printf '\n!!! %s — rolling back\n' "$1" >&2
  journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
  # The downgrade needs the new code (it holds revision 003), so it goes first.
  if [ "$MIGRATED" = 1 ]; then (cd api && venv/bin/alembic downgrade 002) || true; fi
  if [ -n "$PREV_BRANCH" ]; then git checkout -q -B "$PREV_BRANCH" "$PREV_SHA"; else git checkout -q "$PREV_SHA"; fi
  systemctl restart "$SERVICE"; sleep 6
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    echo "    Rolled back to ${PREV_BRANCH:-detached} @ $(git rev-parse --short HEAD); dashboard healthy." >&2
  else
    echo "    Rolled back but the dashboard is still unhealthy — see docs/BCP_AND_ROLLBACK.md. Backups: $BK" >&2
  fi
  exit 1
}

healthy() { curl -fsS -o /dev/null "$1"; }
wait_healthy() {
  for _ in $(seq 1 12); do sleep 5; healthy "$1" && return 0; done
  return 1
}
# A route that exists answers 401/403 to an anonymous request; a missing one 404.
route_code() { curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:5004$1"; }

# ------------------------------------------------------------- deploy
say "Code → $BRANCH @ $(git rev-parse --short "$NEW_SHA")"
git checkout -q -B "$BRANCH" "$NEW_SHA"

if [ "$MIGRATE" = 1 ]; then
  say "Database: alembic upgrade head"
  MIGRATED=1
  (cd api && venv/bin/alembic upgrade head) || rollback "migration failed"
fi

say "Restarting $SERVICE"
systemctl restart "$SERVICE"
wait_healthy http://127.0.0.1:5004/health || rollback "dashboard not healthy after 60s"
for _ in $(seq 1 8); do
  CODE=$(route_code /api/seo/playbook)
  case "$CODE" in 401|403) ;; *) rollback "Playbook route answered $CODE on a worker (wanted 401/403)" ;; esac
  CODE=$(route_code /api/seo/articles)
  case "$CODE" in 401|403) ;; *) rollback "article list answered $CODE (wanted 401/403)" ;; esac
done
echo "    dashboard healthy, Playbook routes mounted on every worker"

say "Score snapshot with the new code — must match exactly"
(cd api && venv/bin/python -m scripts.playbook_score_parity --out "$BK/parity-after.json") || \
  rollback "the scoring snapshot failed with the new code"
(cd api && venv/bin/python -m scripts.playbook_score_parity \
   --compare "$BK/parity-before.json" "$BK/parity-after.json") || rollback "scores changed"

say "Frontend build (about 1-2 minutes)"
if ! (cd web && npm run build) || [ ! -f web/out/index.html ]; then
  printf '\n!!! The frontend build failed. Putting the previous build back.\n' >&2
  rm -rf web/out
  [ -f "$BK/web-out.tgz" ] && tar -C web -xzf "$BK/web-out.tgz"
  echo "    The API is on the new code with the flag off, which the old screens work with." >&2
  echo "    Nothing else needs undoing. Send this output to Claude." >&2
  exit 2
fi

say "Checking from outside"
PAGE=000
for _ in $(seq 1 6); do
  PAGE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC/dashboard/seo/articles/write/" || true)
  [ "$PAGE" = 200 ] && break
  sleep 5
done
[ "$PAGE" = 200 ] || { printf '\n!!! The writer page answered %s from outside (wanted 200).\n    Send this output to Claude.\n' "$PAGE" >&2; exit 2; }

say "Done — Blog Playbook deployed with the flag OFF"
echo "    Scores: identical for every article (see $BK/parity-*.json)."
echo "    Next: the website step, then bash /root/blog-playbook-flag.sh me"
