#!/usr/bin/env bash
# Backlink Ops — trigger one automatic review pass (v1.1).
#
# Cron, hourly inside working hours. The server clock is UTC; 09:00–20:00 IST
# is 03:30–14:30 UTC, so:
#   30 3-14 * * *  cd /var/www/agenticai-dashboard && ops/auto-review.sh >> /var/log/backlink-ops-autoreview.log 2>&1
#
# Needs BACKLINK_OPS_CRON_SECRET in ops/backlink-ops.env, matching the value
# the service runs with. Without it the endpoint refuses (401) — nothing runs.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env
API="${AUTOREVIEW_API_BASE:-http://127.0.0.1:5004}${BACKLINK_OPS_API_PREFIX:-/api/seo/backlink-ops}"
if [ -z "${BACKLINK_OPS_CRON_SECRET:-}" ]; then
  echo "$(date -Is) ERROR: BACKLINK_OPS_CRON_SECRET is not set in ops/backlink-ops.env" >&2
  exit 1
fi
echo "$(date -Is) auto-review start"
# 10 minutes: a run opens every pending page, one at a time, politely.
curl --silent --show-error --fail-with-body --max-time 600 \
  -X POST "$API/auto-review" \
  -H "X-Backlink-Ops-Cron: $BACKLINK_OPS_CRON_SECRET" \
  -H "Content-Type: application/json"
echo
echo "$(date -Is) auto-review done"
