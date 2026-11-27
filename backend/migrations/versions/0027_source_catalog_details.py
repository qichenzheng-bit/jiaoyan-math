from alembic import op
import sqlalchemy as sa

revision = "0027_source_catalog_details"
down_revision = "0026_bank_filter_facts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("source_catalog_details",
        sa.Column("source_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("category",sa.String(60),nullable=False,server_default=""),
        sa.Column("institution",sa.String(120),nullable=False,server_default=""),
        sa.Column("subject_code",sa.String(40),nullable=False,server_default=""),
        sa.Column("subjects",sa.JSON(),nullable=False,server_default="[]"),
        sa.Column("author",sa.String(180),nullable=False,server_default=""),
        sa.Column("publisher",sa.String(180),nullable=False,server_default=""),
        sa.Column("intake_status",sa.String(20),nullable=False,server_default="unknown"),
        sa.Column("revision",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("updated_at",sa.BigInteger(),nullable=False),
        sa.CheckConstraint("intake_status IN ('unknown','not_started','in_progress','completed','stopped')",name="ck_source_catalog_status"))
    op.create_index("ix_source_catalog_group","source_catalog_details",["category","institution","subject_code"])
    op.create_index("ix_source_catalog_school","source_catalog_details",["institution"])
    op.create_index("ix_source_catalog_year","teaching_resources",["kind","archived","cohort_year","exam_type"])
    op.create_index("ix_catalog_tag_subject","knowledge_point_catalog",["subject","status","chapter","name"])
def downgrade():
    op.drop_index("ix_catalog_tag_subject",table_name="knowledge_point_catalog")
    op.drop_index("ix_source_catalog_year",table_name="teaching_resources")
    op.drop_table("source_catalog_details")
