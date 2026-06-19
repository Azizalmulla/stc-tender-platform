#!/usr/bin/env bash
# Verify the stack is healthy. Exits non-zero if not (used by deploy/rollback).
#
#   ./ops/healthcheck.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE="docker compose"
cd "$APP_DIR"

ok=0

echo "==> Containers"
$COMPOSE ps

# 1) API directly on the loopback port
echo "==> API /health (127.0.0.1:8000)"
for i in $(seq 1 10); do
  if curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "   ✅ API healthy"; ok=1; break
  fi
  echo "   ...waiting ($i/10)"; sleep 3
done
[ "$ok" = 1 ] || { echo "   ❌ API did not become healthy"; echo "   logs: docker compose logs --tail=80 tender-api"; exit 1; }

# 2) Through Caddy on :80 (non-fatal if Caddy not the active proxy yet)
echo "==> /health through Caddy (localhost:80)"
if curl -fsS --max-time 5 http://localhost/health >/dev/null 2>&1; then
  echo "   ✅ Caddy proxy healthy"
else
  echo "   ⚠️  Caddy proxy not responding on :80 (ok if host system-caddy still owns :80)"
fi

echo "✅ Health check passed"
