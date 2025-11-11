"""Add conversations and messages tables

Revision ID: 003
Revises: 002_v2
Create Date: 2025-11-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002_v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversations table
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL UNIQUE,
            user_id VARCHAR(100),
            title VARCHAR(500),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Create indexes for conversations
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);")
    
    # Create messages table
    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Create indexes for messages
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages CASCADE;")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE;")
