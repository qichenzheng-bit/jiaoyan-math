"""Track staged covers and safely reclaim only work-managed generated files."""
from alembic import op
import sqlalchemy as sa

revision = "0033_work_cover_cleanup"
down_revision = "0032_teaching_works"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("files", sa.Column("work_managed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("files", sa.Column("work_retired_at", sa.BigInteger(), nullable=True))
    op.create_table(
        "teaching_work_pending_covers",
        sa.Column("work_id", sa.String(36), sa.ForeignKey("teaching_works.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_teaching_work_pending_covers_file_id", "teaching_work_pending_covers", ["file_id"])


def downgrade():
    raise RuntimeError("Restore a coordinated backup to remove managed work files safely")
