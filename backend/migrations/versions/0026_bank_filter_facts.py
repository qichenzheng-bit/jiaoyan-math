from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.core.bank_filter_facts import filter_facts
revision="0026_bank_filter_facts"
down_revision="0025_question_search"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("teaching_resources",sa.Column("bank_facts",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    db=op.get_bind()
    table=sa.table("teaching_resources",sa.column("id",sa.String()),sa.column("kind",sa.String()),sa.column("content",sa.Text()),sa.column("answer",sa.Text()),sa.column("solution",sa.Text()),sa.column("question_type",sa.String()),sa.column("question_data",sa.JSON()),sa.column("bank_facts",postgresql.JSONB()))
    cursor=""
    while True:
        rows=db.execute(sa.select(table.c.id,table.c.content,table.c.answer,table.c.solution,table.c.question_type,table.c.question_data).where(table.c.kind=="question",table.c.id>cursor).order_by(table.c.id).limit(500)).all()
        if not rows:break
        db.execute(table.update().where(table.c.id==sa.bindparam("rid")).values(bank_facts=sa.bindparam("facts")),[{"rid":r.id,"facts":filter_facts(r.content,r.answer,r.solution,r.question_type,r.question_data)} for r in rows])
        cursor=rows[-1].id
    op.create_index("ix_resource_bank_facts","teaching_resources",["bank_facts"],postgresql_using="gin")
    op.create_index("ix_resource_bank_order","teaching_resources",["kind","archived","updated_at","id"])
def downgrade():
    op.drop_index("ix_resource_bank_order",table_name="teaching_resources")
    op.drop_index("ix_resource_bank_facts",table_name="teaching_resources")
    op.drop_column("teaching_resources","bank_facts")
