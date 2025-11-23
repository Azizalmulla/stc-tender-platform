#!/bin/bash
set -e

echo "Running database migrations..."
cd /app

# Run SQL migration for new fields (safe and idempotent)
echo "Adding new fields to database..."
psql $DATABASE_URL -f add_fields.sql || echo "SQL migration failed or already applied"

# Create conversations tables (safe with IF NOT EXISTS)
echo "Creating conversations tables..."
psql $DATABASE_URL -f create_conversations_table.sql || echo "Conversations table creation failed or already exists"

# Fix Alembic state if needed
echo "Checking Alembic state..."
CURRENT_VERSION=$(psql $DATABASE_URL -t -c "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null | xargs)
echo "Current Alembic version: $CURRENT_VERSION"

# If version is invalid or causing issues, stamp to 003 (last known good)
if [ "$CURRENT_VERSION" = "002" ] || [ -z "$CURRENT_VERSION" ]; then
    echo "⚠️  Invalid Alembic state detected, fixing..."
    psql $DATABASE_URL -c "DELETE FROM alembic_version;" || true
    alembic stamp 003
    echo "✅ Alembic state fixed to revision 003"
fi

# Run Alembic migrations (CRITICAL: must succeed for new columns)
echo "Running Alembic migrations..."
alembic upgrade head
if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully"
else
    echo "❌ Migration failed! Check logs above."
fi

echo "Starting application..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT
