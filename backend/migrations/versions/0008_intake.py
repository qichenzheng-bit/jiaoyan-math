from alembic import op
import sqlalchemy as sa
revision="0008_intake"
down_revision="0007_document_workbench"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("intake_jobs",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("title",sa.String(200),nullable=False),
        sa.Column("subject",sa.String(40),nullable=False),
        sa.Column("input_text",sa.Text(),nullable=False),
        sa.Column("model",sa.String(80),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),
        sa.Column("detail",sa.Text(),nullable=False),
        sa.Column("items",sa.JSON(),nullable=False),
        sa.Column("document_id",sa.String(36),sa.ForeignKey("teaching_documents.id",ondelete="RESTRICT"),nullable=True),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve intake data")
