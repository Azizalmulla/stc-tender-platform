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
    
    # Export tracking (prevents duplicate exports)
    exported_to_stc_at = Column(TIMESTAMP(timezone=True))  # When exported to STC Excel
    
    __table_args__ = (
        Index('idx_tenders_published_at', 'published_at'),
        Index('idx_tenders_deadline', 'deadline'),
        Index('idx_tenders_ministry', 'ministry'),
        Index('idx_tenders_category', 'category'),
        Index('idx_tenders_sector', 'sector'),
        Index('idx_tenders_status', 'status'),
    )


class TenderEmbedding(Base):
    __tablename__ = "tender_embeddings"
    
    tender_id = Column(BigInteger, ForeignKey("tenders.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Vector(1024))  # Voyage AI voyage-law-2 dimension
    
    __table_args__ = (
        Index('idx_tender_embeddings_vector', 'embedding', postgresql_using='ivfflat'),
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
