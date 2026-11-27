"""Source reverse lookups and knowledge directory scopes."""
from alembic import op

revision="0028_source_query_indexes"
down_revision="0027_source_catalog_details"
branch_labels=None
depends_on=None

def upgrade():
    op.create_index("ix_resource_source_reverse","teaching_resources",["source_id","kind","archived"])
    op.create_index("ix_resource_chapter_scope","teaching_resources",["kind","archived","subject","chapter"])
    op.create_index("ix_resource_source_link_reverse","resource_source_links",["source_id","resource_id"])

def downgrade():
    op.drop_index("ix_resource_source_link_reverse",table_name="resource_source_links")
    op.drop_index("ix_resource_chapter_scope",table_name="teaching_resources")
    op.drop_index("ix_resource_source_reverse",table_name="teaching_resources")
