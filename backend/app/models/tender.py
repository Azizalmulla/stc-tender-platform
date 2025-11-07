from sqlalchemy import Column, BigInteger, Text, TIMESTAMP, ARRAY, CheckConstraint, Index, Numeric, ForeignKey, REAL
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
    
    __table_args__ = (
        Index('idx_tenders_published_at', 'published_at'),
        Index('idx_tenders_deadline', 'deadline'),
        Index('idx_tenders_ministry', 'ministry'),
        Index('idx_tenders_category', 'category'),
    )


class TenderEmbedding(Base):
    __tablename__ = "tender_embeddings"
    
    tender_id = Column(BigInteger, ForeignKey("tenders.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Vector(1536))  # text-embedding-3-small dimension
    
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
