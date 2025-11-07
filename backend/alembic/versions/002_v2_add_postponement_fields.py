"""Add postponement and meeting tracking fields (standalone)

Revision ID: 002_v2
Revises: 
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_v2'
down_revision = None  # Standalone migration
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns already exist before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('tenders')]
    
    # Add postponement tracking fields
    if 'is_postponed' not in existing_columns:
        op.add_column('tenders', sa.Column('is_postponed', sa.Boolean(), server_default='false', nullable=True))
    if 'original_deadline' not in existing_columns:
        op.add_column('tenders', sa.Column('original_deadline', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'deadline_history' not in existing_columns:
        op.add_column('tenders', sa.Column('deadline_history', postgresql.JSONB(), nullable=True))
    if 'postponement_reason' not in existing_columns:
        op.add_column('tenders', sa.Column('postponement_reason', sa.Text(), nullable=True))
    
    # Add pre-tender meeting fields
    if 'meeting_date' not in existing_columns:
        op.add_column('tenders', sa.Column('meeting_date', sa.TIMESTAMP(timezone=True), nullable=True))
    if 'meeting_location' not in existing_columns:
        op.add_column('tenders', sa.Column('meeting_location', sa.Text(), nullable=True))
    
    # Create indexes for new fields (check if they exist first)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('tenders')]
    if 'idx_tenders_is_postponed' not in existing_indexes:
        op.create_index('idx_tenders_is_postponed', 'tenders', ['is_postponed'], if_not_exists=True)
    if 'idx_tenders_meeting_date' not in existing_indexes:
        op.create_index('idx_tenders_meeting_date', 'tenders', ['meeting_date'], if_not_exists=True)


def downgrade():
    # Drop indexes (ignore if not exist)
    try:
        op.drop_index('idx_tenders_meeting_date', table_name='tenders')
    except:
        pass
    try:
        op.drop_index('idx_tenders_is_postponed', table_name='tenders')
    except:
        pass
    
    # Drop columns (ignore if not exist)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('tenders')]
    
    if 'meeting_location' in existing_columns:
        op.drop_column('tenders', 'meeting_location')
    if 'meeting_date' in existing_columns:
        op.drop_column('tenders', 'meeting_date')
    if 'postponement_reason' in existing_columns:
        op.drop_column('tenders', 'postponement_reason')
    if 'deadline_history' in existing_columns:
        op.drop_column('tenders', 'deadline_history')
    if 'original_deadline' in existing_columns:
        op.drop_column('tenders', 'original_deadline')
    if 'is_postponed' in existing_columns:
        op.drop_column('tenders', 'is_postponed')
