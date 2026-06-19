#!/usr/bin/env bash
# Roll back to the previously-deployed commit recorded by deploy.sh.
#
#   sudo ./ops/rollback.sh
#
# Code rollback only. If a migration changed data, also restore the DB dump from
# ./backups (see the printed instructions at the end).
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_DIR="$APP_DIR/.deploy-state"
COMPOSE="docker compose"

cd "$APP_DIR"

[ -f "$STATE_DIR/previous_ref" ] || { echo "❌ No previous_ref recorded — nothing to roll back to."; exit 1; }
PREV="$(cat "$STATE_DIR/previous_ref")"

echo "==> Rolling back to $PREV"
git checkout "$PREV"

echo "==> Rebuilding and restarting"
$COMPOSE build
$COMPOSE up -d

echo "==> Health check"
if "$APP_DIR/ops/healthcheck.sh"; then
  echo "✅ Rollback OK — now on $(git rev-parse HEAD)"
else
  echo "❌ Health check still failing after rollback — investigate logs: docker compose logs --tail=100 tender-api"
  exit 1
fi

cat <<'EOF'

If you ALSO need to restore the database to the pre-deploy state:
  latest=$(ls -t ./backups/tender-*.sql.gz | head -1)
  gunzip -c "$latest" | docker compose run --rm -T tender-api sh -c 'psql "$DATABASE_URL"'
EOF
