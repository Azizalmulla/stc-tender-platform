-- Migration: Add export tracking for STC Master Workbook feature
-- Run this on the Neon PostgreSQL database

-- 1. Add exported_to_stc_at column to tenders table
ALTER TABLE tenders 
ADD COLUMN IF NOT EXISTS exported_to_stc_at TIMESTAMP WITH TIME ZONE;

-- 2. Create export_files table to store master workbooks
CREATE TABLE IF NOT EXISTS export_files (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    file_data BYTEA NOT NULL,
    description TEXT,
    file_size INTEGER,
    total_rows_exported INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_export_files_name ON export_files(name);
CREATE INDEX IF NOT EXISTS idx_tenders_exported_to_stc ON tenders(exported_to_stc_at);

-- Verify migration
SELECT 'Migration complete!' as status;
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'tenders' AND column_name = 'exported_to_stc_at';
