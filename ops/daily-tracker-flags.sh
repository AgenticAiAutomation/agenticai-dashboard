#!/usr/bin/env bash
# Daily Tracker / per-site levels / Idea Board / task manager — switch the flags. Run as root on the VPS.
#
#   bash /root/daily-tracker-flags.sh levels    per-person, per-site levels on Backlink Ops
#   bash /root/daily-tracker-flags.sh tracker   + the Daily Tracker on /tasks/
#   bash /root/daily-tracker-flags.sh ideas     + the Idea Board
#   bash /root/daily-tracker-flags.sh tasks     + the task manager (T7: tasks, targets, RAG, Mirror, rewards)
#   bash /root/daily-tracker-flags.sh all       all four at once
#   bash /root/daily-tracker-flags.sh off       all four off (the rollback)
#
# Each step adds to what is on. The flags live in their own systemd drop-in,
# so "off" deletes that file. Data is never deleted: switching off hides the
# feature, switching on again shows the same levels, logs and ideas.
set -euo pipefail

SERVICE=dashboard-api
DROPIN_DIR=/etc/systemd/system/$SERVICE.service.d
DROPIN=$DROPIN_DIR/daily-tracker.conf

stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || stop "Run this as root."

has() { [ -f "$DROPIN" ] && grep -q "$1=1" "$DROPIN"; }
L=0; T=0; I=0; M=0
has FEATURE_PER_PROJECT_LEVELS && L=1
has FEATURE_DAILY_TRACKER && T=1
has FEATURE_IDEA_BOARD && I=1
has FEATURE_TASK_MANAGER && M=1

case "${1:-}" in
  levels)  L=1 ;;
  tracker) T=1 ;;
  ideas)   I=1 ;;
  tasks)   M=1 ;;
  all)     L=1; T=1; I=1; M=1 ;;
  off)     L=0; T=0; I=0; M=0 ;;
  *) stop "Say which: levels, tracker, ideas, tasks, all or off.  Example: bash /root/daily-tracker-flags.sh levels" ;;
esac

if [ "$L$T$I$M" = 0000 ]; then
  rm -f "$DROPIN"
else
  mkdir -p "$DROPIN_DIR"
  {
    echo "# Daily Tracker flags — written by daily-tracker-flags.sh $(date +%F_%T). Delete to turn all off."
    echo "[Service]"
    echo "Environment=\"FEATURE_PER_PROJECT_LEVELS=$L\""
    echo "Environment=\"FEATURE_DAILY_TRACKER=$T\""
    echo "Environment=\"FEATURE_IDEA_BOARD=$I\""
    echo "Environment=\"FEATURE_TASK_MANAGER=$M\""
    echo "Environment=\"DAILY_TRACKER_DB=/var/www/agenticai-dashboard/api/instance/daily_tracker.db\""
    echo "Environment=\"DAILY_TRACKER_BACKUP_DIR=/var/www/agenticai-dashboard/api/backups/daily_tracker\""
  } > "$DROPIN"
fi

systemctl daemon-reload
systemctl restart "$SERVICE"
for _ in $(seq 1 12); do
  sleep 5
  if curl -fsS -o /dev/null http://127.0.0.1:5004/health; then
    echo "Done. Per-site levels: $([ $L = 1 ] && echo ON || echo off) · Daily Tracker: $([ $T = 1 ] && echo ON || echo off) · Idea Board: $([ $I = 1 ] && echo ON || echo off) · Task manager: $([ $M = 1 ] && echo ON || echo off)"
    exit 0
  fi
done
echo "!!! The dashboard is not healthy after the restart. Run: bash /root/daily-tracker-flags.sh off" >&2
exit 1
