"""M04: extend existing resources without replacing IDs or original content."""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa
revision="0005_resource_catalog"
down_revision="0004_chat"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("teaching_resources",sa.Column("code",sa.String(16),nullable=True))
    op.add_column("teaching_resources",sa.Column("exam_type",sa.String(80),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("chapter",sa.String(120),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("question_type",sa.String(20),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("unit_type",sa.String(24),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("source_type",sa.String(16),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("authority_tier",sa.String(24),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("cohort_year",sa.String(12),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("series_key",sa.String(80),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("edition",sa.String(60),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("dedup_reason",sa.String(200),nullable=False,server_default=""))
    for key in ("analysis","proof"):
        op.add_column("teaching_resources",sa.Column(key,sa.Text(),nullable=False,server_default=""))
    op.add_column("teaching_resources",sa.Column("exams",sa.JSON(),nullable=False,server_default=sa.text("'[]'")))
    op.alter_column("teaching_resources","exams",server_default=None)
    for key in ("revision","sources_revision"):
        op.add_column("teaching_resources",sa.Column(key,sa.Integer(),nullable=False,server_default="1"))
    op.add_column("teaching_resources",sa.Column("dedup_override",sa.Boolean(),nullable=False,server_default="false"))
    conn=op.get_bind()
    rows=conn.execute(sa.text("SELECT id,kind FROM teaching_resources ORDER BY id")).all()
    used=set()
    for ident,kind in rows:
        while True:
            code={"question":"Q","knowledge":"K","source":"S"}[kind]+uuid4().hex[:8].upper()
            if code not in used: break
        used.add(code)
        conn.execute(sa.text("UPDATE teaching_resources SET code=:code WHERE id=:id"),{"code":code,"id":ident})
    op.alter_column("teaching_resources","code",nullable=False)
    op.create_unique_constraint("uq_teaching_resources_code","teaching_resources",["code"])
    op.create_table("resource_source_links",
        sa.Column("resource_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("source_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("provenance_role",sa.String(16),primary_key=True),
        sa.Column("original_question_number",sa.String(40),nullable=False),
        sa.Column("page_start",sa.Integer(),nullable=True),
        sa.Column("page_end",sa.Integer(),nullable=True),
        sa.Column("chapter",sa.String(120),nullable=False),
        sa.Column("note",sa.String(300),nullable=False),
        sa.Column("is_primary",sa.Boolean(),nullable=False),
        sa.Column("role_verified",sa.Boolean(),nullable=False),
        sa.CheckConstraint("resource_id <> source_id",name="ck_resource_source_not_self"),
        sa.CheckConstraint("provenance_role IN ('original','reproduced','adapted')",name="ck_resource_source_role"),
        sa.CheckConstraint("(page_start IS NULL OR page_start >= 1) AND (page_end IS NULL OR page_end >= 1) AND (page_start IS NULL OR page_end IS NULL OR page_end >= page_start)",name="ck_resource_source_pages"))
    conn.execute(sa.text("INSERT INTO resource_source_links (resource_id,source_id,provenance_role,original_question_number,chapter,note,is_primary,role_verified) SELECT id,source_id,'original','','','旧主来源关联，角色待核实',true,false FROM teaching_resources WHERE source_id IS NOT NULL"))
    op.create_table("resource_source_versions",
        sa.Column("source_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("version",sa.Integer(),primary_key=True),
        sa.Column("snapshot",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
    source_rows=conn.execute(sa.text("SELECT id,code,title,subject,content,source_type,authority_tier,cohort_year,series_key,edition,exam_type,archived,updated_at FROM teaching_resources WHERE kind='source'")).mappings().all()
    table=sa.table("resource_source_versions",sa.column("source_id",sa.String()),sa.column("version",sa.Integer()),sa.column("snapshot",sa.JSON()),sa.column("created_at",sa.BigInteger()))
    for row in source_rows:
        snapshot=dict(row)
        conn.execute(table.insert().values(source_id=row["id"],version=1,snapshot=snapshot,created_at=row["updated_at"]))
    op.create_table("knowledge_point_catalog",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("code",sa.String(16),nullable=False,unique=True),
        sa.Column("name",sa.String(180),nullable=False),
        sa.Column("name_key",sa.String(200),nullable=False),
        sa.Column("subject",sa.String(40),nullable=False),
        sa.Column("chapter",sa.String(120),nullable=False),
        sa.Column("description",sa.Text(),nullable=False),
        sa.Column("status",sa.String(16),nullable=False),
        sa.Column("replaced_by_id",sa.String(36),sa.ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),nullable=True),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("updated_at",sa.BigInteger(),nullable=False),
        sa.UniqueConstraint("subject","name_key",name="uq_kp_subject_name"),
        sa.CheckConstraint("status IN ('active','disabled','replaced')",name="ck_kp_status"),
        sa.CheckConstraint("replaced_by_id IS NULL OR replaced_by_id <> id",name="ck_kp_not_self"))
    op.create_table("resource_knowledge_links",
        sa.Column("resource_id",sa.String(36),sa.ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("knowledge_id",sa.String(36),sa.ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("role",sa.String(16),nullable=False),
        sa.CheckConstraint("role IN ('core','related')",name="ck_resource_kp_role"))

def downgrade():
    # Do not silently lose newly recorded provenance, proofs or knowledge links.
    raise RuntimeError("M04 is data-preserving on upgrade only; restore a coordinated pre-upgrade backup")
