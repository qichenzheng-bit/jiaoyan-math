from alembic import op
import sqlalchemy as sa
revision="0009_chat_refs"
down_revision="0008_intake"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("chat_messages",sa.Column("resource_refs",sa.JSON(),nullable=False,server_default=sa.text("'[]'")))
    op.alter_column("chat_messages","resource_refs",server_default=None)
def downgrade():
    raise RuntimeError("Restore coordinated backup")
