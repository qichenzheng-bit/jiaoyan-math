"""Small immutable search facets separate from large teaching snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0034_work_facets"
down_revision = "0033_work_cover_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teaching_work_versions", sa.Column("facets", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("video_projects", sa.Column("work_facets", postgresql.JSONB(), nullable=False, server_default="{}"))
    # Only known original video snapshot fields are backfilled; do not invent historical sources or labels.
    op.execute("""
      UPDATE video_projects SET work_facets = jsonb_build_object(
        'knowledge_points', COALESCE(source_snapshot::jsonb->'tags','[]'::jsonb),
        'subjects', CASE WHEN coalesce(source_snapshot->>'subject','') <> ''
          THEN jsonb_build_array(source_snapshot->>'subject') ELSE '[]'::jsonb END)
    """)
    op.create_index("ix_work_version_facets", "teaching_work_versions", ["facets"], postgresql_using="gin")
    op.create_index("ix_video_work_facets", "video_projects", ["work_facets"], postgresql_using="gin")


def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve recorded work facets")
