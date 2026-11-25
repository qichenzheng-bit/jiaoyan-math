"""Knowledge aliases and graph edges."""
from alembic import op
import sqlalchemy as sa
revision="0006_knowledge_graph"
down_revision="0005_resource_catalog"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("knowledge_aliases",
        sa.Column("knowledge_id",sa.String(36),sa.ForeignKey("knowledge_point_catalog.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("normalized",sa.String(180),primary_key=True),
        sa.Column("alias",sa.String(180),nullable=False))
    op.create_table("knowledge_relations",
        sa.Column("source_id",sa.String(36),sa.ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("target_id",sa.String(36),sa.ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("relation_type",sa.String(16),primary_key=True),
        sa.CheckConstraint("source_id <> target_id",name="ck_knowledge_relation_not_self"),
        sa.CheckConstraint("relation_type IN ('contains','related','prerequisite')",name="ck_knowledge_relation_type"))

def downgrade():
    raise RuntimeError("Restore a coordinated pre-upgrade backup to avoid losing graph data")
