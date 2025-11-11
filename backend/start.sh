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

# Try to run Alembic migrations (ignore errors for now)
alembic upgrade head || echo "Alembic migration skipped (may already be at latest version)"

echo "Starting application..."
uvicorn app.main:app --host 0.0.0.0 --port $PORT
