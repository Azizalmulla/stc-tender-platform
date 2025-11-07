"""Add postponement and meeting tracking fields

Revision ID: 002
Revises: 001
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Add postponement tracking fields
    op.add_column('tenders', sa.Column('is_postponed', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('tenders', sa.Column('original_deadline', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('tenders', sa.Column('deadline_history', postgresql.JSONB(), nullable=True))
    op.add_column('tenders', sa.Column('postponement_reason', sa.Text(), nullable=True))
    
    # Add pre-tender meeting fields
    op.add_column('tenders', sa.Column('meeting_date', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('tenders', sa.Column('meeting_location', sa.Text(), nullable=True))
    
    # Create indexes for new fields
    op.create_index('idx_tenders_is_postponed', 'tenders', ['is_postponed'])
    op.create_index('idx_tenders_meeting_date', 'tenders', ['meeting_date'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_tenders_meeting_date', table_name='tenders')
    op.drop_index('idx_tenders_is_postponed', table_name='tenders')
    
    # Drop columns
    op.drop_column('tenders', 'meeting_location')
    op.drop_column('tenders', 'meeting_date')
    op.drop_column('tenders', 'postponement_reason')
    op.drop_column('tenders', 'deadline_history')
    op.drop_column('tenders', 'original_deadline')
    op.drop_column('tenders', 'is_postponed')
