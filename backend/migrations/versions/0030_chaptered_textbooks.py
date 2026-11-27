"""Store large textbook chapters as separate documents under a book manifest."""
from alembic import op
import sqlalchemy as sa
revision="0030_chaptered_textbooks"
down_revision="0029_document_versions"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("teaching_documents",sa.Column("chaptered",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column("teaching_documents",sa.Column("parent_document_id",sa.String(36),nullable=True))
    op.add_column("teaching_documents",sa.Column("chapter_order",sa.Integer(),nullable=False,server_default="0"))
    op.add_column("teaching_documents",sa.Column("chapter_blocks_count",sa.Integer(),nullable=False,server_default="0"))
    op.create_foreign_key("fk_teaching_documents_parent","teaching_documents","teaching_documents",["parent_document_id"],["id"],ondelete="RESTRICT")
    op.create_index("ix_teaching_documents_parent_order","teaching_documents",["parent_document_id","chapter_order"])
def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve chaptered textbooks")
