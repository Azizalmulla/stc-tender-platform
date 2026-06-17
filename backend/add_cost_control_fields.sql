-- Phase 0 cost-control + observability schema changes
-- Safe & idempotent (IF NOT EXISTS everywhere).

-- 1) Idempotency guard for the value/sector/award extraction job
ALTER TABLE tenders ADD COLUMN IF NOT EXISTS value_extracted_at TIMESTAMP WITH TIME ZONE;

-- Index to quickly find tenders that still need value/sector extraction
CREATE INDEX IF NOT EXISTS idx_tenders_value_extracted
    ON tenders(value_extracted_at) WHERE value_extracted_at IS NULL;

COMMENT ON COLUMN tenders.value_extracted_at IS 'When value/sector/award extraction last ran (idempotency guard for /extract-tender-values)';

-- 2) Per-call provider usage / cost log
CREATE TABLE IF NOT EXISTS usage_logs (
    id                 BIGSERIAL PRIMARY KEY,
    provider           VARCHAR(32) NOT NULL,
    model              VARCHAR(64),
    run_type           VARCHAR(48),
    tender_id          BIGINT,
    source_id          VARCHAR(128),
    input_tokens       BIGINT,
    output_tokens      BIGINT,
    estimated_cost_usd NUMERIC(12, 6),
    cache_hit          BOOLEAN DEFAULT FALSE,
    retry_count        BIGINT DEFAULT 0,
    error              TEXT,
    created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_created_at ON usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_logs_provider   ON usage_logs(provider);
CREATE INDEX IF NOT EXISTS idx_usage_logs_run_type   ON usage_logs(run_type);

COMMENT ON TABLE usage_logs IS 'Phase 0: one row per external paid call (Claude/Voyage/Browserless/OpenAI) for cost observability';
