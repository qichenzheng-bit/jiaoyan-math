from alembic import op
import sqlalchemy as sa
revision="0012_intake_intent"
down_revision="0011_video_projects"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("chat_messages",sa.Column("intake_intent",sa.String(16),nullable=True))
    op.add_column("intake_jobs",sa.Column("provenance",sa.JSON(),nullable=True))
    op.add_column("intake_jobs",sa.Column("retry_of",sa.String(36),nullable=True))
    op.create_foreign_key("fk_intake_retry_of","intake_jobs","intake_jobs",["retry_of"],["id"],ondelete="RESTRICT")
    op.create_unique_constraint("uq_intake_retry_of","intake_jobs",["retry_of"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve intake provenance")
