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
