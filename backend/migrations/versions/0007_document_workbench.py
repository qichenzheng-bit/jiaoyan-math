"""Persist document workbench layouts and resource references."""
from alembic import op
import sqlalchemy as sa
revision="0007_document_workbench"
down_revision="0006_knowledge_graph"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("teaching_documents",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("title",sa.String(200),nullable=False),
        sa.Column("kind",sa.String(16),nullable=False),
        sa.Column("subject",sa.String(40),nullable=False),
        sa.Column("source_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),nullable=True),
        sa.Column("blocks",sa.JSON(),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("archived",sa.Boolean(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_table("document_resource_refs",
        sa.Column("document_id",sa.String(36),sa.ForeignKey("teaching_documents.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("resource_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True))

def downgrade():
    raise RuntimeError("Restore a coordinated backup instead of dropping document drafts")
