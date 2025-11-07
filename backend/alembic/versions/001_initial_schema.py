"""initial schema with pgvector

Revision ID: 001
Revises: 
Create Date: 2025-01-06 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create tenders table
    op.create_table('tenders',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('ministry', sa.Text(), nullable=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('tender_number', sa.Text(), nullable=True),
        sa.Column('deadline', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('document_price_kd', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('lang', sa.Text(), nullable=True),
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('summary_ar', sa.Text(), nullable=True),
        sa.Column('summary_en', sa.Text(), nullable=True),
        sa.Column('facts_ar', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('facts_en', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("lang IN ('ar','en','unknown')", name='tenders_lang_check'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
        sa.UniqueConstraint('hash')
    )
    
    # Create indexes on tenders
    op.create_index('idx_tenders_category', 'tenders', ['category'], unique=False)
    op.create_index('idx_tenders_deadline', 'tenders', ['deadline'], unique=False)
    op.create_index('idx_tenders_ministry', 'tenders', ['ministry'], unique=False)
    op.create_index('idx_tenders_published_at', 'tenders', ['published_at'], unique=False)
    op.create_index(op.f('ix_tenders_hash'), 'tenders', ['hash'], unique=False)
    op.create_index(op.f('ix_tenders_url'), 'tenders', ['url'], unique=False)
    
    # Create tender_embeddings table
    op.create_table('tender_embeddings',
        sa.Column('tender_id', sa.BigInteger(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('tender_id')
    )
    
    # Create vector index for similarity search (IVFFlat works with 1536 dimensions)
    op.execute("""
        CREATE INDEX idx_tender_embeddings_vector 
        ON tender_embeddings 
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
    
    # Create keyword_hits table
    op.create_table('keyword_hits',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tender_id', sa.BigInteger(), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.Column('match_type', sa.Text(), nullable=False),
        sa.Column('score', sa.REAL(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("match_type IN ('exact','phrase','semantic')", name='keyword_hits_match_type_check'),
        sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes on keyword_hits
    op.create_index('idx_keyword_hits_keyword', 'keyword_hits', ['keyword'], unique=False)
    op.create_index('idx_keyword_hits_tender_id', 'keyword_hits', ['tender_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_keyword_hits_tender_id', table_name='keyword_hits')
    op.drop_index('idx_keyword_hits_keyword', table_name='keyword_hits')
    op.drop_table('keyword_hits')
    
    op.execute('DROP INDEX IF EXISTS idx_tender_embeddings_vector')
    op.drop_table('tender_embeddings')
    
    op.drop_index(op.f('ix_tenders_url'), table_name='tenders')
    op.drop_index(op.f('ix_tenders_hash'), table_name='tenders')
    op.drop_index('idx_tenders_published_at', table_name='tenders')
    op.drop_index('idx_tenders_ministry', table_name='tenders')
    op.drop_index('idx_tenders_deadline', table_name='tenders')
    op.drop_index('idx_tenders_category', table_name='tenders')
    op.drop_table('tenders')
    
    op.execute('DROP EXTENSION IF EXISTS vector')
