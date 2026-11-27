from alembic import op
import sqlalchemy as sa
revision="0023_question_structure"
down_revision="0022_work_agent"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("teaching_resources",sa.Column("question_data",sa.JSON(none_as_null=True),nullable=True))
def downgrade():
    raise RuntimeError("Preserve structured metadata; restore a coordinated backup instead")
