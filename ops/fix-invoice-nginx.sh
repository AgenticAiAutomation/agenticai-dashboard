#!/usr/bin/env bash
# Invoice Desk — put /invoices back on dashboard.agenticaiautomation.co. Run as root.
#
#   bash /root/fix-invoice-nginx.sh          show what it would change, then ask
#   bash /root/fix-invoice-nginx.sh --yes    change it
#
# Found 15 Oct 2026: /invoices/ and /api/invoices/ on the dashboard domain
# answer with the dashboard's own index page, so the desk and client fill links
# (/invoices/f/<token>) do not open. The desk itself is healthy on :5004.
# The 1 Oct deploy added `include snippets/invoice-desk.conf;` above the FIRST
# /seo/backlink-ops block in the site file. If that file has more than one
# server block (port 80 + certbot's 443), the include can sit in the wrong one.
#
# This adds the include to EVERY server block that proxies /seo/backlink-ops
# and has no /invoices yet. It tests with nginx -t, reloads, checks from
# outside, and puts the old file back if anything fails. Plain POSIX awk
# (Ubuntu's default awk is mawk).
set -euo pipefail

REPO=/var/www/agenticai-dashboard
SITE=/etc/nginx/sites-available/dashboard-frontend
SNIPPET=/etc/nginx/snippets/invoice-desk.conf
PUBLIC=https://dashboard.agenticaiautomation.co
STAMP=$(date +%Y%m%d-%H%M%S)

stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || stop "Run this as root."
[ -f "$SITE" ] || stop "$SITE not found."
command -v nginx >/dev/null || stop "nginx not found."

echo "==> What is there now"
echo "    server blocks in $SITE:"
awk '/^[[:space:]]*server[[:space:]]*\{/ { n++; printf "      block %d starts at line %d\n", n, NR }
     /^[[:space:]]*listen/                { printf "        %s\n", $0 }
     /^[[:space:]]*server_name/           { printf "        %s\n", $0 }
     /invoice-desk\.conf|location[^{]*\/invoices/ { printf "        line %d: %s\n", NR, $0 }
     /location[^{]*\/seo\/backlink-ops/   { printf "        line %d: %s\n", NR, $0 }' "$SITE"
echo "    snippet file: $([ -f "$SNIPPET" ] && echo present || echo MISSING)"
CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{size_download}' "$PUBLIC/api/invoices/health" || true)
echo "    $PUBLIC/api/invoices/health -> $CODE (the dashboard index page is 200 4141)"

# The new site file: the include added once per server block that has a
# /seo/backlink-ops location but no invoice include / location.
NEW=$(mktemp)
awk '
  function flush(   i) {
    for (i = 1; i <= m; i++) {
      if (i == first && need) print "    include snippets/invoice-desk.conf;"
      print buf[i]
    }
    m = 0; first = 0; need = 0; has_inv = 0; has_bo = 0
  }
  {
    line = $0
    if (depth == 0 && line ~ /^[[:space:]]*server[[:space:]]*\{/) inblock = 1
    o = gsub(/\{/, "{", line); c = gsub(/\}/, "}", line)
    if (inblock) {
      buf[++m] = $0
      if ($0 ~ /invoice-desk\.conf|location[^{]*\/invoices/) has_inv = 1
      if ($0 ~ /location[^{]*\/seo\/backlink-ops/ && !first) { first = m; has_bo = 1 }
      depth += o - c
      if (depth == 0) { need = (has_bo && !has_inv); if (need) added++; flush(); inblock = 0 }
      next
    }
    depth += o - c
    print $0
  }
  END { if (m) flush(); print added + 0 > "/dev/stderr" }
' "$SITE" > "$NEW" 2> "$NEW.count"
ADD=$(cat "$NEW.count")

if [ "$ADD" = 0 ] && [ ! -f "$SNIPPET" ] && grep -q 'include snippets/invoice-desk.conf' "$SITE"; then
  # Found 22 Oct 2026: the include is there but the snippet file is gone, so
  # the nginx config on disk is invalid (nginx keeps running an older one in
  # memory; the next reload or certbot renewal would fail). Put it back.
  rm -f "$NEW" "$NEW.count"
  [ -f "$REPO/infra/nginx-invoice-desk.conf" ] || stop "$REPO/infra/nginx-invoice-desk.conf not found."
  echo
  echo "==> Change: restore $SNIPPET from the repo"
  cp "$REPO/infra/nginx-invoice-desk.conf" "$SNIPPET"
  if ! nginx -t; then
    rm -f "$SNIPPET"
    stop "nginx config test still fails with the snippet back — removed it again. Send this output to Claude."
  fi
  systemctl reload nginx
  H=""
  for _ in $(seq 1 6); do
    sleep 3
    H=$(curl -s -m 10 "$PUBLIC/api/invoices/health" || true)
    echo "$H" | grep -q '"feature": *"invoice-desk"' && break
  done
  echo "$H" | grep -q '"feature": *"invoice-desk"' || { echo "!!! nginx reloaded but the desk still does not answer. Send this output to Claude." >&2; exit 1; }
  BO=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC/seo/backlink-ops/" || true)
  [ "$BO" = 200 ] || { echo "!!! Backlink Ops answered $BO after the reload. Send this output to Claude." >&2; exit 1; }
  echo
  echo "==> Done — $PUBLIC/invoices/ is the Invoice Desk again; client fill links work."
  exit 0
fi

if [ "$ADD" = 0 ]; then
  rm -f "$NEW" "$NEW.count"
  echo
  echo "Nothing to add: every server block that serves /seo/backlink-ops already has /invoices,"
  echo "or none does. Send this whole output to Claude — the cause is elsewhere."
  exit 1
fi

echo
echo "==> Change: add the /invoices include to $ADD server block(s)"
diff -u "$SITE" "$NEW" || true
if [ "${1:-}" != --yes ]; then
  OK=""
  while [ -z "$OK" ]; do read -r -p "Apply? Type yes: " OK || stop "No answer."; OK=${OK//$'\r'/}; done
  [ "$OK" = yes ] || { rm -f "$NEW" "$NEW.count"; stop "Cancelled."; }
fi

cp "$SITE" "$SITE.bak-$STAMP"
[ -f "$SNIPPET" ] || cp "$REPO/infra/nginx-invoice-desk.conf" "$SNIPPET"
cat "$NEW" > "$SITE"
rm -f "$NEW" "$NEW.count"
undo() {
  cp "$SITE.bak-$STAMP" "$SITE"
  nginx -t 2>/dev/null && systemctl reload nginx
  printf '\n!!! %s — put the old nginx file back (%s). Send this output to Claude.\n' "$1" "$SITE.bak-$STAMP" >&2
  exit 1
}
nginx -t || undo "nginx config test failed"
systemctl reload nginx

H=""
for _ in $(seq 1 6); do
  sleep 3
  H=$(curl -s -m 10 "$PUBLIC/api/invoices/health" || true)
  echo "$H" | grep -q '"feature": *"invoice-desk"' && break
done
echo "$H" | grep -q '"feature": *"invoice-desk"' || undo "the desk still does not answer on $PUBLIC/api/invoices/health"
PAGE=$(curl -s -m 10 "$PUBLIC/invoices/" | grep -c 'Invoice' || true)
[ "$PAGE" -gt 0 ] || undo "$PUBLIC/invoices/ is still not the Invoice Desk"
BO=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$PUBLIC/seo/backlink-ops/" || true)
[ "$BO" = 200 ] || undo "Backlink Ops answered $BO after the change"

echo
echo "==> Done — $PUBLIC/invoices/ is the Invoice Desk again; client fill links work."
echo "    Old nginx file kept at $SITE.bak-$STAMP"
