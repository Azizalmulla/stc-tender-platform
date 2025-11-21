"""Change embedding dimension from 1536 (OpenAI) to 1024 (Voyage AI)

Revision ID: voyage_embeddings
Revises: 
Create Date: 2025-11-22 01:13:00

This migration changes the vector dimension for embeddings from 1536 to 1024
to support Voyage AI's voyage-law-2 model (optimized for legal documents).

IMPORTANT: This migration will:
1. Drop all existing embeddings (they need to be regenerated)
2. Change the vector dimension to 1024
3. Embeddings will be automatically regenerated on next scrape

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'voyage_embeddings'
down_revision = None  # Set this to your latest migration revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade to Voyage AI embeddings (1024 dimensions)"""
    
    # Drop all existing embeddings (they're incompatible with new dimension)
    op.execute("DELETE FROM tender_embeddings")
    
    # Change vector dimension from 1536 to 1024
    # Note: ALTER COLUMN TYPE for vector requires dropping and recreating
    op.execute("ALTER TABLE tender_embeddings ALTER COLUMN embedding TYPE vector(1024)")
    
    print("✅ Embedding dimension changed to 1024 for Voyage AI")
    print("⚠️  All embeddings deleted - they will be regenerated on next scrape")


def downgrade() -> None:
    """Downgrade back to OpenAI embeddings (1536 dimensions)"""
    
    # Drop all existing embeddings
    op.execute("DELETE FROM tender_embeddings")
    
    # Change back to 1536 dimensions
    op.execute("ALTER TABLE tender_embeddings ALTER COLUMN embedding TYPE vector(1536)")
    
    print("✅ Embedding dimension changed back to 1536 for OpenAI")
    print("⚠️  All embeddings deleted - they will be regenerated on next scrape")
