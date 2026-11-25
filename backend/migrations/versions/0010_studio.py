from alembic import op
import sqlalchemy as sa
revision="0010_studio"
down_revision="0009_chat_refs"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("studio_items",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("kind",sa.String(24),nullable=False),
        sa.Column("title",sa.String(200),nullable=False),
        sa.Column("data",sa.JSON(),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("archived",sa.Boolean(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_studio_items_kind","studio_items",["kind"])
    op.create_table("studio_revisions",
        sa.Column("item_id",sa.String(36),sa.ForeignKey("studio_items.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("revision",sa.Integer(),primary_key=True),
        sa.Column("snapshot",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve studio records")
