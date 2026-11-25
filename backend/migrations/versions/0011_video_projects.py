from alembic import op
import sqlalchemy as sa
revision = "0011_video_projects"
down_revision = "0010_studio"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("video_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("teaching_resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("resource_revision", sa.Integer(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("engine_id", sa.String(32), nullable=True, unique=True),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("studio_items.id", ondelete="RESTRICT"), nullable=True, unique=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("resource_id", "resource_revision", name="uq_video_resource_revision"))
def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve video projects")
