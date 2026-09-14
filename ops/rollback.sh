#!/usr/bin/env bash
# Backlink Ops — rollback, three levels. Start at 1 and only escalate.
#
#   ops/rollback.sh --off              L1  disable the feature   ~10s, no data loss
#   ops/rollback.sh --to <tag|sha>     L2  revert the code       ~30s, no data loss
#   ops/rollback.sh --restore <file>   L3  restore the feature DB from a backup
#
# L1 is almost always the right answer. It leaves every backlink, keyword and
# approval in place; re-enabling brings them all back.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env
MODE=${1:-}; ARG=${2:-}

case "$MODE" in
  --off)
    echo "==> L1: disabling the feature"
    ENVFILE="${SYSTEMD_ENV_FILE:-/etc/default/$SERVICE}"
    if [ -w "$ENVFILE" ] || sudo test -w "$ENVFILE"; then
      sudo sed -i 's/^BACKLINK_OPS_ENABLED=.*/BACKLINK_OPS_ENABLED=0/' "$ENVFILE" || \
        echo "BACKLINK_OPS_ENABLED=0" | sudo tee -a "$ENVFILE" >/dev/null
    else
      echo "    could not write $ENVFILE — set BACKLINK_OPS_ENABLED=0 by hand" >&2
    fi
    sudo systemctl restart "$SERVICE"
    sleep 5
    curl -s -o /dev/null -w 'dashboard http %{http_code}\n' "$BASELINE_URL"
    echo "Feature off. Data untouched. Re-enable by setting the flag back to 1."
    ;;

  --to)
    [ -n "$ARG" ] || { echo "usage: rollback.sh --to <tag|sha>" >&2; exit 2; }
    echo "==> L2: reverting code to $ARG"
    git -C "$APP_DIR" fetch --tags --quiet || true
    git -C "$APP_DIR" reset --hard "$ARG"
    sudo systemctl restart "$SERVICE"
    sleep 8
    ops/healthcheck.sh || echo "still unhealthy — escalate to L3 or restore the host backup" >&2
    ;;

  --restore)
    [ -n "$ARG" ] || { echo "usage: rollback.sh --restore <backup.db>" >&2; exit 2; }
    [ -f "$ARG" ] || { echo "no such backup: $ARG" >&2; exit 2; }
    echo "==> L3: restoring the feature database from $ARG"
    TARGET="$APP_DIR/${BACKLINK_OPS_DB:-instance/backlink_ops.db}"
    sudo systemctl stop "$SERVICE"
    cp "$TARGET" "$TARGET.displaced-$(date +%s)" 2>/dev/null || true
    cp "$ARG" "$TARGET"
    sudo systemctl start "$SERVICE"
    sleep 6
    ops/healthcheck.sh
    echo "Restored. The displaced file is kept beside it, nothing was deleted."
    ;;

  *)
    sed -n '2,12p' "$0"
    exit 2
    ;;
esac
