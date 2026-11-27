"""Persistent teaching works, independent of temporary render jobs."""
from alembic import op
import sqlalchemy as sa

revision = "0032_teaching_works"
down_revision = "0031_document_history_limit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teaching_works",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("origin_scope", sa.String(16), nullable=False),
        sa.Column("origin_id", sa.String(36), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("subject", sa.String(40), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("user_id", "origin_scope", "origin_id", "variant", name="uq_work_origin_variant"),
    )
    op.create_index("ix_teaching_works_user_updated", "teaching_works", ["user_id", "updated_at", "id"])
    op.create_table(
        "teaching_work_versions",
        sa.Column("work_id", sa.String(36), sa.ForeignKey("teaching_works.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "teaching_work_assets",
        sa.Column("work_id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("role", sa.String(20), primary_key=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["work_id", "version"], ["teaching_work_versions.work_id", "teaching_work_versions.number"], ondelete="CASCADE"),
    )
    op.create_index("ix_teaching_work_assets_file_id", "teaching_work_assets", ["file_id"])


def downgrade():
    raise RuntimeError("Restore a coordinated backup to remove teaching works safely")
