#!/bin/bash
# Cron driver for the SEO module.
#
# Install:
#   cp infra/seo-cron.sh /usr/local/bin/seo-cron
#   chmod 755 /usr/local/bin/seo-cron
#   crontab -e   # then add the schedule below
#
# Schedule (server clock is UTC; 06:00 IST = 00:30 UTC):
#   30 0 * * *   /usr/local/bin/seo-cron daily        >> /var/log/seo-cron.log 2>&1
#   30 0 * * *   /usr/local/bin/seo-cron scrape       >> /var/log/seo-cron.log 2>&1
#   0 20 * * 0   /usr/local/bin/seo-cron weekly       >> /var/log/seo-cron.log 2>&1
#   0 2 1 * *    /usr/local/bin/seo-cron monthly      >> /var/log/seo-cron.log 2>&1
#
# CRON_SECRET must match the value in api/.env. Without it the endpoints
# return 503 and refuse to run at all.
set -euo pipefail

API_BASE="${SEO_API_BASE:-http://127.0.0.1:5004}"
ENV_FILE="${SEO_ENV_FILE:-/var/www/agenticai-dashboard/api/.env}"

if [ -r "$ENV_FILE" ]; then
  CRON_SECRET=$(grep -oP '(?<=^CRON_SECRET=).*' "$ENV_FILE" | tr -d '"' || true)
fi

if [ -z "${CRON_SECRET:-}" ]; then
  echo "$(date -Is) ERROR: CRON_SECRET not found in $ENV_FILE" >&2
  exit 1
fi

case "${1:-}" in
  daily)   ENDPOINT=daily-audit ;;
  weekly)  ENDPOINT=weekly-audit ;;
  monthly) ENDPOINT=monthly-audit ;;
  scrape)  ENDPOINT=reddit-quora-scrape ;;
  *)
    echo "usage: seo-cron {daily|weekly|monthly|scrape}" >&2
    exit 2
    ;;
esac

echo "$(date -Is) running ${ENDPOINT}"

# --fail-with-body so a non-2xx still prints the API's explanation into the log
# rather than failing silently.
curl --silent --show-error --fail-with-body \
  --max-time 600 \
  -X POST "${API_BASE}/api/seo/cron/${ENDPOINT}" \
  -H "X-Cron-Secret: ${CRON_SECRET}" \
  -H "Content-Type: application/json"

status=$?
echo
echo "$(date -Is) ${ENDPOINT} finished with status ${status}"
exit $status
