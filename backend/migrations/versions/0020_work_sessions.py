from alembic import op
import sqlalchemy as sa
revision="0020_work_sessions"
down_revision="0019_unify_knowledge_points"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("work_sessions",sa.Column("id",sa.String(36),primary_key=True),sa.Column("title",sa.String(200),nullable=False),sa.Column("created_at",sa.BigInteger(),nullable=False),sa.Column("updated_at",sa.BigInteger(),nullable=False))
    op.create_table("work_materials",sa.Column("id",sa.String(36),primary_key=True),sa.Column("session_id",sa.String(36),sa.ForeignKey("work_sessions.id",ondelete="RESTRICT"),nullable=False),sa.Column("file_id",sa.String(36),sa.ForeignKey("files.id",ondelete="RESTRICT"),nullable=False),sa.Column("total_units",sa.Integer(),nullable=True),sa.Column("created_at",sa.BigInteger(),nullable=False),sa.UniqueConstraint("session_id","file_id",name="uq_work_material_file"))
    op.create_index("ix_work_materials_session_id","work_materials",["session_id"])
    op.create_table("work_batches",sa.Column("id",sa.String(36),primary_key=True),sa.Column("material_id",sa.String(36),sa.ForeignKey("work_materials.id",ondelete="RESTRICT"),nullable=False),sa.Column("start",sa.Integer(),nullable=False),sa.Column("end",sa.Integer(),nullable=False),sa.Column("units",sa.JSON(),nullable=False),sa.Column("verified_text",sa.Text(),nullable=True),sa.Column("import_id",sa.String(36),sa.ForeignKey("intake_imports.id",ondelete="RESTRICT"),nullable=True),sa.Column("job_id",sa.String(36),sa.ForeignKey("intake_jobs.id",ondelete="RESTRICT"),nullable=True,unique=True),sa.Column("created_at",sa.BigInteger(),nullable=False),sa.Column("updated_at",sa.BigInteger(),nullable=False),sa.UniqueConstraint("material_id","start","end",name="uq_work_batch_range"))
    op.create_index("ix_work_batches_material_id","work_batches",["material_id"])
def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve work sessions")
