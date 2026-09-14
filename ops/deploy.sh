#!/usr/bin/env bash
# Backlink Ops — deploy with an automatic rollback gate.
#
# The gate is the point of this script: if the dashboard is not healthy within
# 60 seconds of the restart, it puts the previous commit back and restarts
# again, without waiting for a human. Worst case the team loses about a minute.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env
STAMP=$(date +%Y%m%d-%H%M%S)

PREV=$(git -C "$APP_DIR" rev-parse HEAD)
echo "==> previous commit $PREV"

echo "==> preflight"
ops/preflight.sh

echo "==> pulling $BRANCH"
git -C "$APP_DIR" pull --ff-only origin "$BRANCH"

echo "==> dependency check (this feature adds none)"
if ! git -C "$APP_DIR" diff --quiet "$PREV" HEAD -- requirements.txt pyproject.toml 2>/dev/null; then
  echo "    dependency file changed — installing"
  "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" || \
    pip install -r "$APP_DIR/requirements.txt"
else
  echo "    unchanged — nothing to install"
fi

echo "==> restarting $SERVICE"
sudo systemctl restart "$SERVICE"

echo "==> health gate (60s)"
for i in $(seq 1 12); do
  sleep 5
  if ops/healthcheck.sh; then
    echo "==> healthy after $((i*5))s"
    ops/stamp-feature-log.sh "deploy" "$(git -C "$APP_DIR" rev-parse --short HEAD)" || true
    exit 0
  fi
  echo "    not healthy yet ($((i*5))s)"
done

echo "!!! HEALTH GATE FAILED — rolling back to $PREV" >&2
git -C "$APP_DIR" reset --hard "$PREV"
sudo systemctl restart "$SERVICE"
sleep 8
ops/healthcheck.sh && echo "Rolled back and healthy." || \
  echo "Rolled back but still unhealthy — escalate, see docs/BCP_AND_ROLLBACK.md" >&2
exit 1
