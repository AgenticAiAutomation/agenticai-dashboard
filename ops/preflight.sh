#!/usr/bin/env bash
# Backlink Ops — run BEFORE any deploy. Creates every artefact a rollback needs.
#   1. tags the exact commit currently serving traffic
#   2. backs up the main dashboard database AND the feature database
#   3. records the current health so "it was already broken" is answerable
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ops/backlink-ops.env ] && . ops/backlink-ops.env
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backups/preflight/$STAMP"
mkdir -p "$OUT"

echo "==> commit currently serving traffic"
git -C "$APP_DIR" rev-parse HEAD | tee "$OUT/commit.txt"
git -C "$APP_DIR" tag -f "pre-backlink-ops-$STAMP"
echo "    tagged pre-backlink-ops-$STAMP"

echo "==> database backups"
for db in $(find "$APP_DIR" -maxdepth 3 -name '*.db' -o -maxdepth 3 -name '*.sqlite3' 2>/dev/null); do
  sqlite3 "$db" ".backup '$OUT/$(basename "$db")'" && echo "    $db"
done
if command -v pg_dump >/dev/null && [ -n "${DATABASE_URL:-}" ]; then
  pg_dump "$DATABASE_URL" > "$OUT/postgres.sql" && echo "    postgres dump"
fi

echo "==> current health (recorded, not enforced)"
curl -s -o "$OUT/baseline.json" -w 'baseline http %{http_code}\n' --max-time 15 "$BASELINE_URL" || true

echo "==> route inventory before the change"
( cd "$APP_DIR" && python3 - <<'PY' > "$OLDPWD/$OUT/routes-before.txt" 2>/dev/null || true
import importlib, os
for cand in ("api.app.main:app", "app.main:app", "main:app", "wsgi:app",
             "app:app", "run:app", "app:create_app"):
    mod, _, attr = cand.partition(":")
    try:
        m = importlib.import_module(mod)
        a = getattr(m, attr)
        app = a() if callable(a) and attr.startswith("create") else a
        for r in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            print(r.rule)
        break
    except Exception:
        continue
PY
) || true

echo
echo "Preflight complete → $OUT"
echo "Roll back to this point with:  ops/rollback.sh --to pre-backlink-ops-$STAMP"
