"""File archive state and references."""
from alembic import op
import sqlalchemy as sa

revision = "0002_file_references"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("files", sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table("file_references",
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("owner_type", sa.String(80), primary_key=True),
        sa.Column("owner_id", sa.String(100), primary_key=True))

def downgrade():
    op.drop_table("file_references")
    op.drop_column("files", "archived")
