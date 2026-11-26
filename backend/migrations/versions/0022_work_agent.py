from alembic import op
import sqlalchemy as sa
revision="0022_work_agent"
down_revision="0021_original_purge"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("work_sessions",sa.Column("agent_history",sa.JSON(),nullable=False,server_default=sa.text("'[]'")))
def downgrade():
    raise RuntimeError("Preserve agent history; restore a coordinated backup instead")
