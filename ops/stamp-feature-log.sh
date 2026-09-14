#!/usr/bin/env bash
# Appends one line to the repository's feature log so every change to this
# module is recorded in the same place the rest of the dashboard records its
# changes. Called automatically by deploy.sh; safe to run by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env
LOG="${BACKLINK_OPS_FEATURE_LOG:-docs/FEATURE_LOG.md}"
ACTION="${1:-change}"; REF="${2:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
mkdir -p "$(dirname "$LOG")"
[ -f "$LOG" ] || printf '# Feature log\n\nOne line per change that reaches production.\n\n' > "$LOG"
printf -- '- %s · backlink-ops · %s · %s · by %s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ACTION" "$REF" "${SUDO_USER:-${USER:-unknown}}" >> "$LOG"
echo "stamped $LOG"
