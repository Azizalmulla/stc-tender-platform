-- Fix Alembic version table to match current migration state
-- This resets Alembic to the correct revision

-- First, check what's in the table
SELECT * FROM alembic_version;

-- Update to the correct current revision (003 is the last one that ran successfully)
UPDATE alembic_version SET version_num = '003';

-- Verify
SELECT * FROM alembic_version;
