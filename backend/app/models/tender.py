from sqlalchemy import Column, BigInteger, Text, TIMESTAMP, ARRAY, CheckConstraint, Index, Numeric, ForeignKey, REAL, Boolean, String, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.db.session import Base


class Tender(Base):
    __tablename__ = "tenders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    url = Column(Text, unique=True, nullable=False, index=True)
    title = Column(Text)
    body = Column(Text)
    ministry = Column(Text)
    category = Column(Text)
    tender_number = Column(Text)
    deadline = Column(TIMESTAMP(timezone=True))
    document_price_kd = Column(Numeric(10, 3))
    published_at = Column(TIMESTAMP(timezone=True))
    lang = Column(Text, CheckConstraint("lang IN ('ar','en','unknown')"))
    attachments = Column(JSONB)
    summary_ar = Column(Text)
    summary_en = Column(Text)
    facts_ar = Column(ARRAY(Text))
    facts_en = Column(ARRAY(Text))
    hash = Column(Text, unique=True, nullable=False, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Postponement tracking
    is_postponed = Column(Boolean, default=False)
    original_deadline = Column(TIMESTAMP(timezone=True))
    deadline_history = Column(JSONB)  # Array of {deadline, changed_at, reason}
    postponement_reason = Column(Text)
    
    # Pre-tender meeting info
    meeting_date = Column(TIMESTAMP(timezone=True))
    meeting_location = Column(Text)
    
    # STC Export fields
    bidding_company = Column(String)  # STC, SSTC, ePortal, CDN, JMT, AlDar, H3
    sector = Column(String)  # Government, Oil & Gas, Banking, Private, Telecom
    tender_type = Column(String)  # CTC, Semi-Tender, RFP, RFQ, etc.
    tender_fee = Column(Numeric(10, 2))
    release_date = Column(Date)
    expected_value = Column(Numeric(15, 2))
    status = Column(String, server_default='Released')  # Released, Future, Awarded, Opened, Cancelled
    awarded_vendor = Column(String)
    awarded_value = Column(Numeric(15, 2))
    award_date = Column(TIMESTAMP(timezone=True))  # When the award was announced
    parent_tender_id = Column(BigInteger, ForeignKey("tenders.id", ondelete="SET NULL"))  # Links award notice to original tender
    justification = Column(String)
    announcement_type = Column(String)  # Awarding, Complaint, Opening Envelopes, etc.
    
    # AI Enrichment fields (background processed)
    ai_relevance_score = Column(String)  # very_high, high, medium, low
    ai_confidence = Column(REAL)  # 0.0 to 1.0
    ai_keywords = Column(ARRAY(Text))  # Technical keywords extracted
    ai_sectors = Column(ARRAY(Text))  # Matching STC sectors
    ai_recommended_team = Column(String)  # Which STC team should handle this
    ai_reasoning = Column(Text)  # Why it's relevant/not relevant
    ai_processed_at = Column(TIMESTAMP(timezone=True))  # When AI analysis was done
    value_extracted_at = Column(TIMESTAMP(timezone=True))  # When value/sector/award extraction last ran (idempotency guard)
    
    # Phase 2 — document-intelligence / extraction-quality fields
    title_ar = Column(Text)                       # Real Arabic subject/title of the tender
    title_en = Column(Text)                       # Real English title (derived/translated)
    source_label = Column(Text)                   # Legacy synthetic label e.g. "<number> - Edition N"
    tender_number_confidence = Column(REAL)       # 0.0–1.0 confidence in tender_number
    tender_number_candidates = Column(JSONB)      # All plausible numbers seen on the block
    deadline_confidence = Column(REAL)            # 0.0–1.0 confidence in deadline
    deadline_missing_reason = Column(Text)        # Why deadline is absent (not silently null)
    extraction_json = Column(JSONB)               # Full structured model output for this tender block
    extraction_quality_status = Column(Text)      # clean | needs_review | failed
    extraction_warnings = Column(ARRAY(Text))     # e.g. multi_tender_page, ambiguous_tender_number...
    sector_details = Column(JSONB)                # [{name, confidence, reason}] conservative tagging
    source_page_block_index = Column(BigInteger)  # Which block on the page this row came from
    needs_review = Column(Boolean, server_default='false')  # Flagged for human review
    
    # Export tracking (prevents duplicate exports)
    exported_to_stc_at = Column(TIMESTAMP(timezone=True))  # When exported to STC Excel
    
    __table_args__ = (
        Index('idx_tenders_published_at', 'published_at'),
        Index('idx_tenders_deadline', 'deadline'),
        Index('idx_tenders_ministry', 'ministry'),
        Index('idx_tenders_category', 'category'),
        Index('idx_tenders_sector', 'sector'),
        Index('idx_tenders_status', 'status'),
        Index('idx_tenders_tender_number', 'tender_number'),
        Index('idx_tenders_announcement_type', 'announcement_type'),
        Index('idx_tenders_quality_status', 'extraction_quality_status'),
        Index('idx_tenders_needs_review', 'needs_review'),
    )


class TenderEmbedding(Base):
    __tablename__ = "tender_embeddings"
    
    tender_id = Column(BigInteger, ForeignKey("tenders.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Vector(1024))  # Voyage AI voyage-law-2 dimension
    
    __table_args__ = (
        Index('idx_tender_embeddings_vector', 'embedding', postgresql_using='ivfflat'),
    )


class Client(Base):
    __tablename__ = "clients"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # Company name (e.g. "STC", "KNPC")
    chat_id = Column(String, unique=True, index=True)  # Telegram chat ID for notifications
    sectors = Column(ARRAY(Text), nullable=False, server_default='{}')  # Allowed sectors
    is_active = Column(Boolean, server_default='true')
    api_key = Column(String, unique=True)  # Optional API key for programmatic access
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_clients_chat_id', 'chat_id'),
        Index('idx_clients_is_active', 'is_active'),
    )


class UsageLog(Base):
    """Per-call provider usage / cost-observability log (Phase 0).

    One row per external paid call (Claude, Voyage, Browserless, OpenAI...).
    Written best-effort: failures here must never break the pipeline.
    """
    __tablename__ = "usage_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)        # anthropic | voyage | browserless | openai
    model = Column(String)                            # e.g. claude-sonnet-4-6, voyage-law-2
    run_type = Column(String)                         # ocr | summarize | extract | value_sector | relevance | embedding | chat_answer | query_analysis | screenshot
    tender_id = Column(BigInteger)                    # nullable; source row if applicable
    source_id = Column(String)                        # nullable; external id (edition/page, etc.)
    input_tokens = Column(BigInteger)
    output_tokens = Column(BigInteger)
    estimated_cost_usd = Column(Numeric(12, 6))
    cache_hit = Column(Boolean, server_default='false')
    retry_count = Column(BigInteger, server_default='0')
    error = Column(Text)                              # error message if the call failed
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_usage_logs_created_at', 'created_at'),
        Index('idx_usage_logs_provider', 'provider'),
        Index('idx_usage_logs_run_type', 'run_type'),
    )


class KeywordHit(Base):
    __tablename__ = "keyword_hits"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tender_id = Column(BigInteger, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(Text, nullable=False)
    match_type = Column(Text, CheckConstraint("match_type IN ('exact','phrase','semantic')"), nullable=False)
    score = Column(REAL)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_keyword_hits_tender_id', 'tender_id'),
        Index('idx_keyword_hits_keyword', 'keyword'),
    )
