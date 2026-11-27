"""Retain two historical revisions per composition document; remove stale image ownership."""
from alembic import op

revision="0031_document_history_limit"
down_revision="0030_chaptered_textbooks"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("""
        WITH ranked AS (
          SELECT v.document_id,v.revision,
                 row_number() OVER(PARTITION BY v.document_id ORDER BY v.revision DESC) AS n
          FROM teaching_document_versions v JOIN teaching_documents d ON d.id=v.document_id
          WHERE v.revision<d.revision
        ), stale AS (SELECT document_id,revision FROM ranked WHERE n>2)
        DELETE FROM file_references f USING stale s
        WHERE f.owner_type='document_version'
          AND f.owner_id=s.document_id || ':' || s.revision::text
    """)
    op.execute("""
        WITH ranked AS (
          SELECT v.document_id,v.revision,
                 row_number() OVER(PARTITION BY v.document_id ORDER BY v.revision DESC) AS n
          FROM teaching_document_versions v JOIN teaching_documents d ON d.id=v.document_id
          WHERE v.revision<d.revision
        )
        DELETE FROM teaching_document_versions v USING ranked r
        WHERE v.document_id=r.document_id AND v.revision=r.revision AND r.n>2
    """)

def downgrade():
    raise RuntimeError("Deleted old history cannot be reconstructed; use a coordinated backup")
