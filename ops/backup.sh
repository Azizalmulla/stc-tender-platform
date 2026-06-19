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

# Report client vs server versions up front so a version mismatch is obvious.
echo "==> Version check (pg_dump client vs Postgres server)"
$COMPOSE run --rm -T tender-api sh -c '
  echo "    client : $(pg_dump --version)"
  echo "    server : $(psql "$DATABASE_URL" -tAc "show server_version" 2>/dev/null || echo "unreachable")"
' || echo "    ⚠️  could not read versions — continuing"

echo "==> Dumping database -> $out"
# -T: no TTY; pg_dump reads DATABASE_URL from the container env (env_file: .env).
# Check the pipeline result explicitly: with `set -e` a bare failing pipe would
# abort the script BEFORE the cleanup below, leaving a bogus partial .gz behind.
# `if ! ...` disables set -e for this line; pipefail makes the status reflect pg_dump.
if ! $COMPOSE run --rm -T tender-api sh -c 'pg_dump "$DATABASE_URL"' | gzip > "$out"; then
  echo "❌ pg_dump failed — removing partial file"; rm -f "$out"; exit 1
fi

# Fail loudly if the dump is suspiciously tiny (e.g. pg_dump returned 0 but empty).
size=$(wc -c < "$out" | tr -d ' ')
if [ "$size" -lt 200 ]; then
  echo "❌ Backup looks empty ($size bytes) — check DATABASE_URL"; rm -f "$out"; exit 1
fi
echo "   ✅ Backup written ($size bytes)"

echo "==> Pruning old backups (keeping $KEEP)"
ls -t "$BACKUP_DIR"/tender-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "   ✅ Done"
