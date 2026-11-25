from alembic import op
import sqlalchemy as sa
revision="0014_material_import"
down_revision="0013_intake_sources"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("intake_imports",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("file_id",sa.String(36),sa.ForeignKey("files.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("text",sa.Text(),nullable=False),
        sa.Column("metadata_json",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_intake_imports_file_id","intake_imports",["file_id"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve material imports")
