#!/usr/bin/env bash
# Dump the tender database to ./backups (gzip). Works for both managed (Neon)
# and self-hosted Postgres because pg_dump runs inside the API image using the
# DATABASE_URL from .env. Keeps the most recent 14 dumps.
#
#   ./ops/backup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE="docker compose"
BACKUP_DIR="$APP_DIR/backups"
KEEP="${KEEP:-14}"

cd "$APP_DIR"
mkdir -p "$BACKUP_DIR"

ts="$(date -u +%Y%m%d-%H%M%S)"
out="$BACKUP_DIR/tender-$ts.sql.gz"

echo "==> Dumping database -> $out"
# -T: no TTY; pg_dump reads DATABASE_URL from the container env (env_file: .env).
$COMPOSE run --rm -T tender-api sh -c 'pg_dump "$DATABASE_URL"' | gzip > "$out"

# Fail loudly if the dump is suspiciously tiny (e.g. auth error produced 0 rows).
size=$(wc -c < "$out" | tr -d ' ')
if [ "$size" -lt 200 ]; then
  echo "❌ Backup looks empty ($size bytes) — check DATABASE_URL"; rm -f "$out"; exit 1
fi
echo "   ✅ Backup written ($size bytes)"

echo "==> Pruning old backups (keeping $KEEP)"
ls -t "$BACKUP_DIR"/tender-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "   ✅ Done"
