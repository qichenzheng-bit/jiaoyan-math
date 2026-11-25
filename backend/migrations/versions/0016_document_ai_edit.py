from alembic import op
import sqlalchemy as sa
revision="0016_document_ai_edit"
down_revision="0015_intake_supplement"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("document_ai_edits",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("document_id",sa.String(36),sa.ForeignKey("teaching_documents.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("base_revision",sa.Integer(),nullable=False),
        sa.Column("base_blocks",sa.JSON(),nullable=False),
        sa.Column("fields",sa.JSON(),nullable=False),
        sa.Column("instruction",sa.Text(),nullable=False),
        sa.Column("model",sa.String(80),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),
        sa.Column("detail",sa.Text(),nullable=False),
        sa.Column("changes",sa.JSON(),nullable=False),
        sa.Column("accepted",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_document_ai_edits_document_id","document_ai_edits",["document_id"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve document AI edit history")
