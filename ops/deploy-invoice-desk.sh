#!/usr/bin/env bash
# Invoice Desk + Backlink Ops v1.2 — one-shot deploy, run as root on the VPS.
#
#   bash /root/deploy-invoice-desk.sh          (asks before changing anything)
#   bash /root/deploy-invoice-desk.sh --yes    (you've already seen the commit list)
#
# Checks before it changes anything, shows what will go live and asks first.
# If the dashboard or the desk is not healthy after the restart, it puts back
# the previous commit, unit and nginx config by itself and restarts again.
# Data is never touched: the desk's SQLite file is new, and a rollback leaves it.
set -euo pipefail

REPO=/var/www/agenticai-dashboard
BRANCH=feat/invoice-desk
SERVICE=dashboard-api
DROPIN_DIR=/etc/systemd/system/$SERVICE.service.d
DROPIN=$DROPIN_DIR/invoice-desk.conf
SITE=/etc/nginx/sites-available/dashboard-frontend
SNIPPET=/etc/nginx/snippets/invoice-desk.conf
PUBLIC=https://dashboard.agenticaiautomation.co
STAMP=$(date +%Y%m%d-%H%M%S)

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
git merge-base --is-ancestor HEAD "$NEW_SHA" || \
  stop "The live code has commits that $BRANCH doesn't contain — deploying would drop them."

[ -x api/venv/bin/pip ] || stop "No venv at $REPO/api/venv."
command -v nginx >/dev/null || stop "nginx not found."
[ -f "$SITE" ] || stop "$SITE not found."
# Already set up if the site includes our snippet (what this script adds) or
# has /invoices blocks pasted in by hand. Adding them twice fails nginx -t.
if grep -qE 'invoice-desk\.conf|location[^{]*/invoices' "$SITE"; then
  NGINX_DONE=1
else
  NGINX_DONE=0
  # Goes just above the existing Backlink Ops blocks (they live in the right
  # server block); failing that, above the one and only `location / {`.
  ANCHOR='^\s*location\s+/seo/backlink-ops'
  if ! grep -qE "$ANCHOR" "$SITE"; then
    ANCHOR='^\s*location\s+/\s*\{'
    N=$(grep -cE "$ANCHOR" "$SITE" || true)
    [ "$N" = 1 ] || stop "Couldn't find one clear place in $SITE for the /invoices blocks (found $N). Add infra/nginx-invoice-desk.conf by hand — see docs/INVOICE_DESK.md."
  fi
fi

say "These commits will go live"
git log --oneline "HEAD..$NEW_SHA"
NEW_REQS=$(git diff "HEAD" "$NEW_SHA" -- api/requirements.txt | grep -E '^\+[^+#[:space:]]' | sed 's/^+//' || true)
echo
echo "    new Python packages: ${NEW_REQS:-none}"
echo "    nginx: $([ "$NGINX_DONE" = 1 ] && echo 'already has /invoices — left alone' || echo "add /invoices + /api/invoices to $SITE")"
echo "    systemd: INVOICE_DESK_* settings in $DROPIN"
echo
if [ "${1:-}" = --yes ]; then
  echo "Deploy? yes (given as --yes)"
else
  # Some consoles (browser / Windows) send Enter as CR+LF, which arrives here
  # as an empty answer before anyone types — so blank lines are skipped.
  OK=""
  while [ -z "$OK" ]; do
    read -r -p "Deploy? Type yes to continue: " OK || stop "No answer."
    OK=${OK//$'\r'/}
  done
  [ "$OK" = yes ] || stop "Cancelled."
fi

# ------------------------------------------------------------- rollback
ROLLED=0
rollback() {
  [ "$ROLLED" = 1 ] && return; ROLLED=1
  printf '\n!!! %s — rolling back\n' "$1" >&2
  journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
  if [ -n "$PREV_BRANCH" ]; then git checkout -q -B "$PREV_BRANCH" "$PREV_SHA"; else git checkout -q "$PREV_SHA"; fi
  # 2. put back the settings file that was there before, rather than deleting it
  if [ -f "$DROPIN.bak-$STAMP" ]; then cp "$DROPIN.bak-$STAMP" "$DROPIN"; else rm -f "$DROPIN"; fi
  systemctl daemon-reload
  if [ -f "$SITE.bak-$STAMP" ]; then
    cp "$SITE.bak-$STAMP" "$SITE"; rm -f "$SNIPPET"
    nginx -t 2>/dev/null && systemctl reload nginx
  fi
  systemctl restart "$SERVICE"; sleep 6
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    echo "    Rolled back to ${PREV_BRANCH:-detached} @ $(git rev-parse --short HEAD); dashboard healthy." >&2
  else
    echo "    Rolled back but the dashboard is still unhealthy — see docs/BCP_AND_ROLLBACK.md." >&2
  fi
  exit 1
}

healthy() { curl -fsS -o /dev/null "$1"; }
wait_healthy() {
  for _ in $(seq 1 12); do sleep 5; healthy "$1" && return 0; done
  return 1
}

# ------------------------------------------------------------- deploy
say "Code → $BRANCH @ $(git rev-parse --short "$NEW_SHA")"
git checkout -q -B "$BRANCH" "$NEW_SHA"

if [ -n "$NEW_REQS" ]; then
  say "Installing: $NEW_REQS"
  # shellcheck disable=SC2086
  api/venv/bin/pip install -q $NEW_REQS || rollback "pip install failed"
fi

say "Data folders (owned by www-data)"
mkdir -p api/instance api/backups/invoice_desk
chown www-data:www-data api/instance api/backups api/backups/invoice_desk

say "systemd settings → $DROPIN"
mkdir -p "$DROPIN_DIR"
[ -f "$DROPIN" ] && cp "$DROPIN" "$DROPIN.bak-$STAMP"
{ echo "# Invoice Desk — added by ops/deploy-invoice-desk.sh $STAMP. Delete this file to remove."
  echo "[Service]"
  grep -E '^Environment="INVOICE_DESK_' infra/dashboard-api.service; } > "$DROPIN"
systemctl daemon-reload

say "Restarting $SERVICE"
systemctl restart "$SERVICE"
wait_healthy http://127.0.0.1:5004/health || rollback "dashboard not healthy after 60s"
wait_healthy http://127.0.0.1:5004/api/invoices/health || rollback "invoice desk did not come up"
for _ in $(seq 1 8); do
  healthy http://127.0.0.1:5004/api/invoices/health || rollback "invoice desk missing on one of the workers"
done
echo "    dashboard + invoice desk healthy"

if [ "$NGINX_DONE" = 0 ]; then
  say "nginx: /invoices blocks (backup at $SITE.bak-$STAMP)"
  cp "$SITE" "$SITE.bak-$STAMP"
  cp infra/nginx-invoice-desk.conf "$SNIPPET"
  sed -i -E "0,\#$ANCHOR#s##    include snippets/invoice-desk.conf;\n&#" "$SITE"
  nginx -t || rollback "nginx config test failed"
  systemctl reload nginx
fi

say "Checking from outside"
for _ in $(seq 1 6); do
  sleep 5
  CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC/api/invoices/health" || true)
  PAGE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC/invoices/" || true)
  [ "$CODE" = 200 ] && [ "$PAGE" = 200 ] && break
done
if [ "$CODE" != 200 ] || [ "$PAGE" != 200 ]; then
  # The desk already answered on the server itself, so the code is fine; a
  # failure here is nginx or DNS. Undo nginx only if this run changed it.
  [ "$NGINX_DONE" = 0 ] && rollback "public URLs answered $CODE / $PAGE after the nginx change"
  printf '\n!!! The desk runs on the server, but from outside it answered %s / %s (wanted 200 / 200).\n' "$CODE" "$PAGE" >&2
  echo "    Nothing was rolled back. Send this output to Claude." >&2
  exit 2
fi

say "Done — live at $PUBLIC/invoices/"
echo "    Before the first invoice: Settings → business address + bank details (issuing is refused until both are set)."
echo "    Undo the desk only (10s, keeps data): delete $DROPIN, systemctl daemon-reload, systemctl restart $SERVICE"
