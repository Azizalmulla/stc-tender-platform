#!/usr/bin/env bash
# Deploy the tender platform on the VPS (VPS-only, no Render).
#
#   sudo ./ops/deploy.sh [git-ref]
#
# Steps: preflight -> snapshot current ref -> pull -> DB backup -> build ->
#        migrate (idempotent) -> up -d -> healthcheck.
# On healthcheck failure it tells you exactly how to roll back.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE_DIR="$APP_DIR/.deploy-state"
COMPOSE="docker compose"
REF="${1:-}"

cd "$APP_DIR"
mkdir -p "$STATE_DIR"

echo "==> Preflight"
command -v docker >/dev/null || { echo "❌ docker not installed"; exit 1; }
$COMPOSE version >/dev/null || { echo "❌ docker compose plugin missing"; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo "❌ $APP_DIR/.env missing — copy .env.example and fill it in"; exit 1; }
[ -f "$APP_DIR/docker-compose.yml" ] || { echo "❌ docker-compose.yml missing"; exit 1; }

# Save the currently-deployed commit so rollback.sh can return to it.
CURRENT_REF="$(git rev-parse HEAD)"
echo "$CURRENT_REF" > "$STATE_DIR/previous_ref"
echo "==> Snapshotted current ref: $CURRENT_REF"

if [ -n "$REF" ]; then
  echo "==> Fetching and checking out $REF"
  git fetch --all --prune
  git checkout "$REF"
  git pull --ff-only || true
else
  echo "==> Pulling latest on current branch"
  git pull --ff-only || echo "   (no upstream / not fast-forward — using working tree as-is)"
fi

echo "==> Backing up database (best effort)"
"$APP_DIR/ops/backup.sh" || echo "   ⚠️  backup failed/skipped — continuing"

echo "==> Building images"
$COMPOSE build

echo "==> Running idempotent migrations"
"$APP_DIR/ops/migrate.sh"

echo "==> Starting web stack"
$COMPOSE up -d

echo "==> Health check"
if "$APP_DIR/ops/healthcheck.sh"; then
  echo "✅ Deploy OK — now on $(git rev-parse HEAD)"
else
  echo "❌ Health check FAILED."
  echo "   Roll back with:  ./ops/rollback.sh"
  exit 1
fi
