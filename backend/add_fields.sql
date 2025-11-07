-- Add postponement and meeting fields if they don't exist
-- This script is idempotent and safe to run multiple times

-- Add is_postponed column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='is_postponed') THEN
        ALTER TABLE tenders ADD COLUMN is_postponed BOOLEAN DEFAULT false;
    END IF;
END $$;

-- Add original_deadline column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='original_deadline') THEN
        ALTER TABLE tenders ADD COLUMN original_deadline TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Add deadline_history column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='deadline_history') THEN
        ALTER TABLE tenders ADD COLUMN deadline_history JSONB;
    END IF;
END $$;

-- Add postponement_reason column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='postponement_reason') THEN
        ALTER TABLE tenders ADD COLUMN postponement_reason TEXT;
    END IF;
END $$;

-- Add meeting_date column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='meeting_date') THEN
        ALTER TABLE tenders ADD COLUMN meeting_date TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Add meeting_location column
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='meeting_location') THEN
        ALTER TABLE tenders ADD COLUMN meeting_location TEXT;
    END IF;
END $$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_tenders_is_postponed ON tenders(is_postponed);
CREATE INDEX IF NOT EXISTS idx_tenders_meeting_date ON tenders(meeting_date);
