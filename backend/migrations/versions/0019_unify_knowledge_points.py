"""Backfill legacy resource knowledge names into the existing ID-based catalog.

Unresolved ambiguous aliases and subjectless resources are preserved, never deleted.
"""
from alembic import op
import sqlalchemy as sa
import unicodedata
from uuid import uuid4
from time import time

revision="0019_unify_knowledge_points"
down_revision="0018_question_difficulty"
branch_labels=None
depends_on=None

def norm(v):
    return unicodedata.normalize("NFKC",v).strip().casefold()

def upgrade():
    conn=op.get_bind()
    meta=sa.MetaData()
    resource=sa.Table("teaching_resources",meta,autoload_with=conn)
    point=sa.Table("knowledge_point_catalog",meta,autoload_with=conn)
    alias=sa.Table("knowledge_aliases",meta,autoload_with=conn)
    link=sa.Table("resource_knowledge_links",meta,autoload_with=conn)
    points={(p.subject,p.name_key):p for p in conn.execute(sa.select(point)).mappings()}
    aliases={}
    for p in conn.execute(sa.select(alias.c.normalized,point.c.subject,point.c.id).join(point,point.c.id==alias.c.knowledge_id).where(point.c.status=="active")):
        aliases.setdefault((p.subject,p.normalized),set()).add(p.id)
    known=set(conn.execute(sa.select(link.c.resource_id,link.c.knowledge_id)).all())
    now=int(time())
    for r in conn.execute(sa.select(resource.c.id,resource.c.subject,resource.c.chapter,resource.c.tags).where(resource.c.kind.in_(("question","knowledge")))).mappings():
        if not r.subject:continue
        for name in r.tags or []:
            if not isinstance(name,str):continue
            name=name.strip();key=norm(name)
            if not key or len(name)>180 or len(key)>200:continue
            p=points.get((r.subject,key))
            if p:
                ident=p.replaced_by_id if p.status=="replaced" and p.replaced_by_id else p.id
            else:
                candidates=aliases.get((r.subject,key),set())
                if len(candidates)>1:continue
                if candidates:ident=next(iter(candidates))
                else:
                    ident=str(uuid4())
                    values=dict(id=ident,code="KP"+uuid4().hex[:8].upper(),name=name,name_key=key,subject=r.subject,chapter=r.chapter,description="",status="active",replaced_by_id=None,revision=1,created_at=now,updated_at=now)
                    conn.execute(point.insert().values(**values))
                    p=conn.execute(sa.select(point).where(point.c.id==ident)).mappings().one()
                    points[(r.subject,key)]=p
            if (r.id,ident) not in known:
                conn.execute(link.insert().values(resource_id=r.id,knowledge_id=ident,role="related"))
                known.add((r.id,ident))

def downgrade():
    raise RuntimeError("Restore a coordinated pre-upgrade backup; knowledge relationships must not be discarded")
