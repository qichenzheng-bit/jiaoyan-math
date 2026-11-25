"""Independent teaching resources; no video or legacy account data."""
from alembic import op
import sqlalchemy as sa
revision = "0003_teaching_resources"
down_revision = "0002_file_references"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("teaching_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("subject", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("teaching_resources.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False))
    for col in ("kind", "subject", "fingerprint"):
        op.create_index("ix_teaching_resources_"+col, "teaching_resources", [col])

def downgrade():
    op.drop_table("teaching_resources")
