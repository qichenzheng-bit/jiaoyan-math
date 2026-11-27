"""Persistent version snapshots for composition documents and textbook chapters."""
from alembic import op
import sqlalchemy as sa

revision="0029_document_versions"
down_revision="0028_source_query_indexes"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table(
        "teaching_document_versions",
        sa.Column("document_id",sa.String(36),sa.ForeignKey("teaching_documents.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("snapshot",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.PrimaryKeyConstraint("document_id","revision",name="pk_teaching_document_versions"))
    op.create_index("ix_teaching_document_versions_created_at","teaching_document_versions",["created_at"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve document version history")
