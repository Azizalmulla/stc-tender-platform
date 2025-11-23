-- Add STC export fields to tenders table (safe, idempotent)

DO $$ 
BEGIN
    -- bidding_company
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='bidding_company') THEN
        ALTER TABLE tenders ADD COLUMN bidding_company VARCHAR;
        RAISE NOTICE 'Added column: bidding_company';
    ELSE
        RAISE NOTICE 'Column bidding_company already exists, skipping';
    END IF;

    -- sector
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='sector') THEN
        ALTER TABLE tenders ADD COLUMN sector VARCHAR;
        RAISE NOTICE 'Added column: sector';
    ELSE
        RAISE NOTICE 'Column sector already exists, skipping';
    END IF;

    -- tender_type
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='tender_type') THEN
        ALTER TABLE tenders ADD COLUMN tender_type VARCHAR;
        RAISE NOTICE 'Added column: tender_type';
    ELSE
        RAISE NOTICE 'Column tender_type already exists, skipping';
    END IF;

    -- tender_fee
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='tender_fee') THEN
        ALTER TABLE tenders ADD COLUMN tender_fee NUMERIC(10, 2);
        RAISE NOTICE 'Added column: tender_fee';
    ELSE
        RAISE NOTICE 'Column tender_fee already exists, skipping';
    END IF;

    -- release_date
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='release_date') THEN
        ALTER TABLE tenders ADD COLUMN release_date DATE;
        RAISE NOTICE 'Added column: release_date';
    ELSE
        RAISE NOTICE 'Column release_date already exists, skipping';
    END IF;

    -- expected_value
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='expected_value') THEN
        ALTER TABLE tenders ADD COLUMN expected_value NUMERIC(15, 2);
        RAISE NOTICE 'Added column: expected_value';
    ELSE
        RAISE NOTICE 'Column expected_value already exists, skipping';
    END IF;

    -- status
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='status') THEN
        ALTER TABLE tenders ADD COLUMN status VARCHAR DEFAULT 'Released';
        RAISE NOTICE 'Added column: status';
    ELSE
        RAISE NOTICE 'Column status already exists, skipping';
    END IF;

    -- awarded_vendor
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='awarded_vendor') THEN
        ALTER TABLE tenders ADD COLUMN awarded_vendor VARCHAR;
        RAISE NOTICE 'Added column: awarded_vendor';
    ELSE
        RAISE NOTICE 'Column awarded_vendor already exists, skipping';
    END IF;

    -- awarded_value
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='awarded_value') THEN
        ALTER TABLE tenders ADD COLUMN awarded_value NUMERIC(15, 2);
        RAISE NOTICE 'Added column: awarded_value';
    ELSE
        RAISE NOTICE 'Column awarded_value already exists, skipping';
    END IF;

    -- justification
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='justification') THEN
        ALTER TABLE tenders ADD COLUMN justification VARCHAR;
        RAISE NOTICE 'Added column: justification';
    ELSE
        RAISE NOTICE 'Column justification already exists, skipping';
    END IF;

    -- announcement_type
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='tenders' AND column_name='announcement_type') THEN
        ALTER TABLE tenders ADD COLUMN announcement_type VARCHAR;
        RAISE NOTICE 'Added column: announcement_type';
    ELSE
        RAISE NOTICE 'Column announcement_type already exists, skipping';
    END IF;

END $$;
