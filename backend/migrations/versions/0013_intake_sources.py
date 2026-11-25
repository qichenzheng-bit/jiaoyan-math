from alembic import op
import sqlalchemy as sa
revision="0013_intake_sources"
down_revision="0012_intake_intent"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("intake_jobs",sa.Column("source_id",sa.String(36),nullable=True))
    op.create_foreign_key("fk_intake_source","intake_jobs","teaching_resources",["source_id"],["id"],ondelete="RESTRICT")
    op.create_index("ix_intake_jobs_source_id","intake_jobs",["source_id"])
    op.execute("UPDATE intake_jobs SET source_id = (SELECT source_id FROM teaching_documents WHERE teaching_documents.id = intake_jobs.document_id) WHERE document_id IS NOT NULL")

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve intake source associations")
