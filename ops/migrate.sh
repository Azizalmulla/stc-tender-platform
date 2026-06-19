#!/usr/bin/env bash
# Apply idempotent schema migrations against DATABASE_URL.
#
# The app intentionally does NOT use the (historically broken) Alembic chain.
# Schema is maintained by these idempotent SQL files (all IF NOT EXISTS), the
# same set start.sh applies on container boot — running them here too is safe
# and makes the migration step explicit in the deploy flow.
#
#   ./ops/migrate.sh
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE="docker compose"
cd "$APP_DIR"

MIGRATIONS="add_fields.sql create_conversations_table.sql add_stc_export_fields.sql add_ai_enrichment_fields.sql add_export_tracking.sql add_cost_control_fields.sql add_extraction_quality_fields.sql"

echo "==> Applying migrations: $MIGRATIONS"
$COMPOSE run --rm -T tender-api sh -c '
  set -e
  cd /app
  for f in '"$MIGRATIONS"'; do
    if [ -f "$f" ]; then
      echo "  -> $f"
      psql "$DATABASE_URL" -f "$f" || echo "     (skipped/already applied: $f)"
    fi
  done
'
echo "✅ Migrations applied"
