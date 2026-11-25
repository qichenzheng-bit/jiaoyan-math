"""Persistent chat history independent from CLI."""
from alembic import op
import sqlalchemy as sa
revision="0004_chat"
down_revision="0003_teaching_resources"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("chat_sessions",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("title",sa.String(160),nullable=False),
        sa.Column("project",sa.String(100),nullable=False),
        sa.Column("pinned",sa.Boolean(),nullable=False),
        sa.Column("archived",sa.Boolean(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_table("chat_messages",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("session_id",sa.String(36),sa.ForeignKey("chat_sessions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("position",sa.Integer(),nullable=False),
        sa.Column("role",sa.String(16),nullable=False),
        sa.Column("content",sa.Text(),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),
        sa.Column("detail",sa.Text(),nullable=False),
        sa.Column("model",sa.String(80),nullable=False),
        sa.Column("attachments",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_chat_messages_session_id","chat_messages",["session_id"])

def downgrade():
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
