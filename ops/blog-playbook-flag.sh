#!/usr/bin/env bash
# Blog Playbook — switch the flag. Run as root on the VPS.
#
#   bash /root/blog-playbook-flag.sh me      on for Jai's login only
#   bash /root/blog-playbook-flag.sh team    on for every SEO login
#   bash /root/blog-playbook-flag.sh off     off for everyone (the rollback),
#                                            including access ticked on the Users page
#
# Day to day, admins grant access on Users → "Blog Playbook access" instead.
#
# The setting lives in its own systemd drop-in, so "off" simply deletes that
# file. Publishing never depends on the flag; off = the team works as before.
set -euo pipefail

REPO=/var/www/agenticai-dashboard
SERVICE=dashboard-api
DROPIN_DIR=/etc/systemd/system/$SERVICE.service.d
DROPIN=$DROPIN_DIR/blog-playbook.conf
JAI=jai.prajapati91@gmail.com

stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || stop "Run this as root."
MODE=${1:-}
EMAIL=${2:-$JAI}

case "$MODE" in
  me|team)
    DB_URL=$(grep -E '^DATABASE_URL=' "$REPO/api/.env" | head -1 | cut -d= -f2- | tr -d '"'"'" | sed 's/+psycopg2//')
    FOUND=$(psql "$DB_URL" -tAc "SELECT count(*) FROM users WHERE lower(email) = lower('$EMAIL')" 2>/dev/null || echo "?")
    if [ "$FOUND" = 0 ]; then
      echo "No dashboard login uses $EMAIL. Logins with admin rights:"
      psql "$DB_URL" -tAc "SELECT email FROM users WHERE role IN ('admin','owner') ORDER BY email" 2>/dev/null || true
      stop "Run again with the right email: bash /root/blog-playbook-flag.sh $MODE you@example.com"
    fi
    mkdir -p "$DROPIN_DIR"
    {
      echo "# Blog Playbook flag — written by blog-playbook-flag.sh $(date +%F_%T). Delete to turn off."
      echo "[Service]"
      echo "Environment=\"BLOG_PLAYBOOK_USERS=$EMAIL\""
      if [ "$MODE" = team ]; then echo 'Environment="BLOG_PLAYBOOK_ENABLED=true"'; fi
    } > "$DROPIN"
    ;;
  off)
    rm -f "$DROPIN"
    # Access ticked on the Users page lives here; moved aside, not deleted, so
    # the list can be put back by renaming it.
    ACCESS=$REPO/api/instance/blog_playbook_access.json
    if [ -f "$ACCESS" ]; then mv "$ACCESS" "$ACCESS.off-$(date +%Y%m%d-%H%M%S)"; fi
    ;;
  *)
    stop "Say which: me, team or off.  Example: bash /root/blog-playbook-flag.sh me"
    ;;
esac

systemctl daemon-reload
systemctl restart "$SERVICE"
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    case "$MODE" in
      me)   echo "Done: Blog Playbook is ON for $EMAIL only. Log out and in again, then open Write an article." ;;
      team) echo "Done: Blog Playbook is ON for every SEO login." ;;
      off)  echo "Done: Blog Playbook is OFF for everyone." ;;
    esac
    exit 0
  fi
done
echo "!!! The dashboard is not healthy after the restart. Run: bash /root/blog-playbook-flag.sh off" >&2
exit 1
