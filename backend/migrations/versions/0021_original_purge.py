from alembic import op
import sqlalchemy as sa
revision="0021_original_purge"
down_revision="0020_work_sessions"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("files",sa.Column("purged_at",sa.BigInteger(),nullable=True))
    op.add_column("files",sa.Column("purge_pending",sa.Boolean(),nullable=False,server_default=sa.false()))
def downgrade():
    raise RuntimeError("Original-file purge history must be preserved; restore a coordinated backup instead")
