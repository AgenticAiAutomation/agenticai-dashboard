#!/usr/bin/env bash
# Invoice Desk — switch /invoices back on for dashboard.agenticaiautomation.co. Run as root.
#
#   bash /root/enable-invoice-nginx.sh
#
# Found 22 Oct 2026: in the nginx file actually loaded, the include line was
# commented out during the 7 Oct outage ("# disabled 2026-10-07 outage:").
# Most likely cause of that outage: /etc/nginx/snippets/invoice-desk.conf was
# missing, and an include of a missing file stops nginx from loading. The
# snippet is back (fix-invoice-nginx.sh, 22 Oct) and nginx -t passes.
#
# This uncomments that one line, tests, reloads and checks Invoices, Backlink
# Ops and the dashboard from outside. Any failure puts the old file back.
set -euo pipefail

SNIPPET=/etc/nginx/snippets/invoice-desk.conf
BKDIR=/root/backups/nginx
PUBLIC=https://dashboard.agenticaiautomation.co
STAMP=$(date +%Y%m%d-%H%M%S)

stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || stop "Run this as root."
[ -f "$SNIPPET" ] || stop "$SNIPPET is missing — run bash /root/fix-invoice-nginx.sh --yes first."
mkdir -p "$BKDIR"

# 22 Oct: the first version of this script left its backup INSIDE
# sites-enabled, where nginx loads it as a second site ("duplicate listen").
# Move any such copies out first, or nginx -t can never pass.
for f in /etc/nginx/sites-enabled/*.bak-* /etc/nginx/sites-enabled/*.bak; do
  [ -e "$f" ] || continue
  echo "==> Moving stray backup out of sites-enabled: $f -> $BKDIR/"
  mv "$f" "$BKDIR/"
done
nginx -t 2>/dev/null || { nginx -t; stop "nginx config does not pass its test even before any change. Send this to Claude."; }

# The file nginx really loads (sites-enabled may be a link or a copy).
FILE=$(grep -lE '^[[:space:]]*#.*include snippets/invoice-desk\.conf' /etc/nginx/sites-enabled/* 2>/dev/null | head -1 || true)
[ -n "$FILE" ] || stop "No commented-out invoice include found in /etc/nginx/sites-enabled/. Send this to Claude."
FILE=$(readlink -f "$FILE")
N=$(grep -cE '^[[:space:]]*#.*include snippets/invoice-desk\.conf' "$FILE")
[ "$N" = 1 ] || stop "Found $N commented invoice includes in $FILE (expected 1). Send this to Claude."
grep -qE '^[[:space:]]*include snippets/invoice-desk\.conf' "$FILE" && stop "An active include is already there."

echo "==> Re-enabling the /invoices include in $FILE"
grep -nE '#.*include snippets/invoice-desk\.conf' "$FILE"
BAK="$BKDIR/$(basename "$FILE").bak-$STAMP"
cp "$FILE" "$BAK"
sed -i -E 's|^[[:space:]]*#.*(include snippets/invoice-desk\.conf;).*$|    \1|' "$FILE"
grep -nE 'include snippets/invoice-desk\.conf' "$FILE"

undo() {
  cp "$BAK" "$FILE"
  nginx -t 2>/dev/null && systemctl reload nginx
  printf '\n!!! %s — put the old file back (%s). Invoices stays off; nothing else changed.\n' "$1" "$BAK" >&2
  exit 1
}
nginx -t || undo "nginx config test failed"
systemctl reload nginx

ok=0
for _ in $(seq 1 6); do
  sleep 3
  if curl -s -m 10 "$PUBLIC/api/invoices/health" | grep -q '"feature": *"invoice-desk"'; then ok=1; break; fi
done
[ "$ok" = 1 ] || undo "the Invoice Desk still does not answer on $PUBLIC/api/invoices/health"
for P in /dashboard/ /seo/backlink-ops/ /invoices/; do
  C=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC$P" || true)
  [ "$C" = 200 ] || undo "$P answered $C after the change"
done

echo
echo "==> Done — $PUBLIC/invoices/ is the Invoice Desk again; client fill links work."
echo "    Old file kept at $BAK"
