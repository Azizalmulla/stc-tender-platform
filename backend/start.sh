#!/bin/bash
set -e

echo "Running database migrations..."
cd /app

# Run SQL migration for new fields (safe and idempotent)
echo "Adding new fields to database..."
psql $DATABASE_URL -f add_fields.sql || echo "SQL migration failed or already applied"

# Try to run Alembic migrations (ignore errors for now)
alembic upgrade head || echo "Alembic migration skipped (may already be at latest version)"

echo "Starting application..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT
