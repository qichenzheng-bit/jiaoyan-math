from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.core.search_features import search_features
revision="0025_question_search"
down_revision="0024_source_occurrences"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("teaching_resources",sa.Column("search_features",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    db=op.get_bind()
    table=sa.table("teaching_resources",sa.column("id",sa.String()),sa.column("kind",sa.String()),sa.column("content",sa.Text()),sa.column("search_features",postgresql.JSONB()))
    cursor=""
    while True:
        rows=db.execute(sa.select(table.c.id,table.c.content).where(table.c.kind=="question",table.c.id>cursor).order_by(table.c.id).limit(500)).all()
        if not rows:break
        db.execute(table.update().where(table.c.id==sa.bindparam("rid")).values(search_features=sa.bindparam("terms")),[{"rid":r.id,"terms":search_features(r.content)} for r in rows])
        cursor=rows[-1].id
    op.create_index("ix_resource_search_features", "teaching_resources",["search_features"],postgresql_using="gin")
def downgrade():
    op.drop_index("ix_resource_search_features",table_name="teaching_resources")
    op.drop_column("teaching_resources","search_features")
