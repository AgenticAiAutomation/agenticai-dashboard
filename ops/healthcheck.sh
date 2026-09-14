#!/usr/bin/env bash
# Backlink Ops — health gate.
# Exits 0 only if BOTH the feature and a pre-existing dashboard route are
# healthy. Used by deploy.sh and safe to run from cron.
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env

fail() { echo "UNHEALTHY: $*" >&2; exit 1; }

code=$(curl -s -o /tmp/bo-health.json -w '%{http_code}' --max-time 15 "$HEALTH_URL" || echo 000)
[ "$code" = "200" ] || fail "feature health returned $code"
grep -q '"db_ok": *true' /tmp/bo-health.json || fail "feature database failed its integrity check"

base=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASELINE_URL" || echo 000)
case "$base" in 2*|3*) ;; *) fail "pre-existing dashboard route returned $base" ;; esac

echo "HEALTHY  feature=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' /tmp/bo-health.json)  baseline=$base"
