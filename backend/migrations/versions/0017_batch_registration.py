from alembic import op
import sqlalchemy as sa
from app.core.content_normalization import question_stem_key
revision="0017_batch_registration"
down_revision="0016_document_ai_edit"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("teaching_resources",sa.Column("stem_key",sa.String(64),nullable=False,server_default=""))
    conn=op.get_bind()
    # Page through existing rows without changing resource IDs or revisions.
    last=""
    while True:
        rows=conn.execute(sa.text("SELECT id,content FROM teaching_resources WHERE kind='question' AND id>:last ORDER BY id LIMIT 500"),{"last":last}).all()
        if not rows:break
        conn.execute(sa.text("UPDATE teaching_resources SET stem_key=:key WHERE id=:id"),[{"id":r.id,"key":question_stem_key(r.content)} for r in rows])
        last=rows[-1].id
    op.create_index("ix_teaching_resources_stem_key","teaching_resources",["stem_key"])
    op.create_table("document_registrations",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("document_id",sa.String(36),sa.ForeignKey("teaching_documents.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("base_revision",sa.Integer(),nullable=False),
        sa.Column("result_revision",sa.Integer(),nullable=False),
        sa.Column("entries",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.BigInteger(),nullable=False))
    op.create_index("ix_document_registrations_document_id","document_registrations",["document_id"])

def downgrade():
    raise RuntimeError("Restore coordinated backup to preserve registration history")
