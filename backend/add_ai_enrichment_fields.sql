-- Add AI enrichment fields to tenders table
-- These store pre-computed relevance analysis from Claude AI

ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_relevance_score VARCHAR(20);
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_confidence REAL;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_keywords TEXT[];
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_sectors TEXT[];
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_recommended_team VARCHAR(100);
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS ai_processed_at TIMESTAMP WITH TIME ZONE;

-- Create index for finding unprocessed tenders
CREATE INDEX IF NOT EXISTS idx_tenders_ai_processed ON tenders(ai_processed_at) WHERE ai_processed_at IS NULL;

-- Create index for relevance filtering
CREATE INDEX IF NOT EXISTS idx_tenders_ai_relevance ON tenders(ai_relevance_score);

COMMENT ON COLUMN tenders.ai_relevance_score IS 'very_high, high, medium, low - computed by Claude AI';
COMMENT ON COLUMN tenders.ai_confidence IS 'Confidence score 0.0-1.0';
COMMENT ON COLUMN tenders.ai_keywords IS 'Technical keywords extracted by AI';
COMMENT ON COLUMN tenders.ai_sectors IS 'Matching STC business sectors';
COMMENT ON COLUMN tenders.ai_recommended_team IS 'Recommended STC team assignment';
COMMENT ON COLUMN tenders.ai_reasoning IS 'AI explanation of relevance';
COMMENT ON COLUMN tenders.ai_processed_at IS 'When AI enrichment was completed';
