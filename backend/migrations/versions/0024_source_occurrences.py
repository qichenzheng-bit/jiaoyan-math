from alembic import op
import sqlalchemy as sa
revision="0024_source_occurrences"
down_revision="0023_question_structure"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("resource_source_links",sa.Column("occurrences",sa.JSON(),nullable=False,server_default=sa.text("'[]'")))
def downgrade():
    raise RuntimeError("Source occurrence history must not be discarded; restore a coordinated backup.")
