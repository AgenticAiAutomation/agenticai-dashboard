#!/bin/bash
# Deploy the dashboard on the VPS: pull, rebuild frontend, restart API, reload nginx.
# Usage: /var/www/agenticai-dashboard/deploy.sh
set -euo pipefail

APP_DIR=/var/www/agenticai-dashboard

cd "$APP_DIR"

echo "==> Pulling latest master"
git pull origin master

echo "==> Installing API dependencies"
./api/venv/bin/pip install -q -r api/requirements.txt

echo "==> Running database migrations"
(cd api && ../api/venv/bin/alembic upgrade head)

echo "==> Building frontend static export"
cd web
npm ci
npm run build
cd "$APP_DIR"

# A failed build leaves web/out stale rather than empty, so fail loudly instead
# of silently serving the previous release.
if [ ! -f web/out/index.html ]; then
  echo "ERROR: web/out/index.html missing — build produced no output. Aborting." >&2
  exit 1
fi

echo "==> Restarting API"
systemctl restart dashboard-api
sleep 5
systemctl is-active --quiet dashboard-api || {
  echo "ERROR: dashboard-api failed to start. Recent logs:" >&2
  journalctl -u dashboard-api -n 30 --no-pager >&2
  exit 1
}

echo "==> Reloading nginx"
nginx -t
systemctl reload nginx

echo "==> Verifying"
curl -fsS http://127.0.0.1:5004/health && echo
curl -fsS -o /dev/null -w "frontend: %{http_code}\n" \
  -H "Host: dashboard.agenticaiautomation.co" http://127.0.0.1/login/

echo "==> Deploy complete"
