"""Preserve selected work file references."""
from alembic import op
import sqlalchemy as sa
revision = "0035_work_handoffs"
down_revision = "0034_work_facets"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("work_handoffs",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("user_id",sa.Integer(),nullable=False),
        sa.Column("purpose",sa.String(16),nullable=False),
        sa.Column("items",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_work_handoffs_user_id","work_handoffs",["user_id"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve references")
