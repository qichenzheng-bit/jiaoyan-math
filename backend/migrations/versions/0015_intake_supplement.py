from alembic import op
import sqlalchemy as sa
revision="0015_intake_supplement"
down_revision="0014_material_import"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("intake_supplements",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("job_id",sa.String(36),sa.ForeignKey("intake_jobs.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("item_uid",sa.String(36),nullable=False),
        sa.Column("base_revision",sa.Integer(),nullable=False),
        sa.Column("base_item",sa.JSON(),nullable=False),
        sa.Column("fields",sa.JSON(),nullable=False),
        sa.Column("instruction",sa.Text(),nullable=False),
        sa.Column("model",sa.String(80),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),
        sa.Column("detail",sa.Text(),nullable=False),
        sa.Column("proposal",sa.JSON(),nullable=False),
        sa.Column("accepted",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_intake_supplements_job_id","intake_supplements",["job_id"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve AI supplements")
