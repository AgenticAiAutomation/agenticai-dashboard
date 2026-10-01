#!/usr/bin/env bash
# Invoice Desk + Backlink Ops v1.2 — one-shot deploy, run as root on the VPS.
#
#   bash /root/deploy-invoice-desk.sh
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
if grep -q 'invoices' "$SITE"; then
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
read -r -p "Deploy? Type yes to continue: " OK
[ "$OK" = yes ] || stop "Cancelled."

# ------------------------------------------------------------- rollback
ROLLED=0
rollback() {
  [ "$ROLLED" = 1 ] && return; ROLLED=1
  printf '\n!!! %s — rolling back\n' "$1" >&2
  journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
  if [ -n "$PREV_BRANCH" ]; then git checkout -q "$PREV_BRANCH"; else git checkout -q "$PREV_SHA"; fi
  rm -f "$DROPIN"; systemctl daemon-reload
  if [ -f "$SITE.bak-$STAMP" ]; then
    cp "$SITE.bak-$STAMP" "$SITE"; rm -f "$SNIPPET"
    nginx -t 2>/dev/null && systemctl reload nginx
  fi
  systemctl restart "$SERVICE"; sleep 6
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    echo "    Rolled back to ${PREV_BRANCH:-$PREV_SHA}; dashboard healthy." >&2
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
{ echo "# Invoice Desk — added by ops/deploy-invoice-desk.sh $STAMP. Delete this file to remove."
  echo "[Service]"
  grep -E '^Environment="INVOICE_DESK_' infra/dashboard-api.service; } > "$DROPIN"
systemctl daemon-reload

say "Restarting $SERVICE"
systemctl restart "$SERVICE"
wait_healthy http://127.0.0.1:5004/health || rollback "dashboard not healthy after 60s"
wait_healthy http://127.0.0.1:5004/api/invoices/health || rollback "invoice desk did not come up"
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
sleep 2
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC/api/invoices/health" || true)
PAGE=$(curl -s -o /dev/null -w '%{http_code}' "$PUBLIC/invoices/" || true)
[ "$CODE" = 200 ] && [ "$PAGE" = 200 ] || rollback "public URLs answered $CODE / $PAGE (wanted 200 / 200)"

say "Done — live at $PUBLIC/invoices/"
echo "    Before the first invoice: Settings → business address + bank details (issuing is refused until both are set)."
echo "    Undo the desk only (10s, keeps data): delete $DROPIN, systemctl daemon-reload, systemctl restart $SERVICE"
