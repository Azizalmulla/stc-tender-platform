-- Phase 2: extraction-quality / document-intelligence columns.
-- All idempotent (IF NOT EXISTS) — safe to run repeatedly and on container boot.

ALTER TABLE tenders ADD COLUMN IF NOT EXISTS title_ar TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS title_en TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS source_label TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS tender_number_confidence REAL;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS tender_number_candidates JSONB;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS deadline_confidence REAL;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS deadline_missing_reason TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS extraction_json JSONB;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS extraction_quality_status TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS extraction_warnings TEXT[];
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS sector_details JSONB;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS source_page_block_index BIGINT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_tenders_quality_status ON tenders(extraction_quality_status);
CREATE INDEX IF NOT EXISTS idx_tenders_needs_review ON tenders(needs_review);
