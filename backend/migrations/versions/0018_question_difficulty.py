from alembic import op
import sqlalchemy as sa
revision="0018_question_difficulty"
down_revision="0017_batch_registration"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("teaching_resources",sa.Column("difficulty",sa.String(16),nullable=False,server_default=""))

def downgrade():
    op.drop_column("teaching_resources","difficulty")
