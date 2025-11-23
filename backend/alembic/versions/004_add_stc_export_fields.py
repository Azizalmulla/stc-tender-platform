"""add_stc_export_fields

Revision ID: 004_add_stc_export_fields
Revises: 003_add_conversations
Create Date: 2025-11-23 07:58:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_add_stc_export_fields'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns for STC Excel export
    op.add_column('tenders', sa.Column('bidding_company', sa.String(), nullable=True))
    op.add_column('tenders', sa.Column('sector', sa.String(), nullable=True))
    op.add_column('tenders', sa.Column('tender_type', sa.String(), nullable=True))
    op.add_column('tenders', sa.Column('tender_fee', sa.Numeric(10, 2), nullable=True))
    op.add_column('tenders', sa.Column('release_date', sa.Date(), nullable=True))
    op.add_column('tenders', sa.Column('expected_value', sa.Numeric(15, 2), nullable=True))
    op.add_column('tenders', sa.Column('status', sa.String(), nullable=True, server_default='Released'))
    op.add_column('tenders', sa.Column('awarded_vendor', sa.String(), nullable=True))
    op.add_column('tenders', sa.Column('awarded_value', sa.Numeric(15, 2), nullable=True))
    op.add_column('tenders', sa.Column('justification', sa.String(), nullable=True))
    op.add_column('tenders', sa.Column('announcement_type', sa.String(), nullable=True))


def downgrade():
    # Remove columns if needed to rollback
    op.drop_column('tenders', 'announcement_type')
    op.drop_column('tenders', 'justification')
    op.drop_column('tenders', 'awarded_value')
    op.drop_column('tenders', 'awarded_vendor')
    op.drop_column('tenders', 'status')
    op.drop_column('tenders', 'expected_value')
    op.drop_column('tenders', 'release_date')
    op.drop_column('tenders', 'tender_fee')
    op.drop_column('tenders', 'tender_type')
    op.drop_column('tenders', 'sector')
    op.drop_column('tenders', 'bidding_company')
