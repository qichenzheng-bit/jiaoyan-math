"""Search metadata captured from a validated export snapshot, not live detail queries. Legacy knowledge_points stores recorded tag names, not knowledge units or video teaching points."""
from sqlalchemy import select
from app.models import TeachingResource, ResourceSourceLink, SourceCatalogDetail


def collect(doc):
    facts = {k:set() for k in ("subjects","knowledge_points","knowledge_tags",
                              "source_types","institutions","years")}
    source_ids, resource_ids = set(), set()
    def add(field, value):
        if isinstance(value,str) and value.strip():
            facts[field].add(value.strip())
    def resource(item):
        add("subjects",item.get("subject"))
        for value in item.get("tags") or []:
            add("knowledge_points",value)
        for value in item.get("knowledge_tags") or []:
            if isinstance(value,dict):
                add("knowledge_tags",value.get("name"))
        if item.get("source_id"):
            source_ids.add(item["source_id"])
    add("subjects",doc.get("subject"))
    if doc.get("source_id"):
        source_ids.add(doc["source_id"])
    for block in doc.get("blocks", []):
        add("subjects",block.get("subject"))
        if block.get("resource_id"):
            resource_ids.add(block["resource_id"])
        ref = block.get("snapshot") or {}
        resource(ref)
        for value in block.get("knowledge_tags") or []:
            if isinstance(value,str):
                add("knowledge_points",value)
    return facts, source_ids, resource_ids


def chunks(items):
    items = sorted(items)
    for i in range(0,len(items),500):
        yield items[i:i+500]


def capture(db, doc, direct_source=None):
    facts, source_ids, resource_ids = collect(doc)
    if direct_source:
        source_ids.add(direct_source)
    for part in chunks(resource_ids):
        source_ids.update(db.scalars(select(ResourceSourceLink.source_id).where(ResourceSourceLink.resource_id.in_(part))))
    sources = []
    for part in chunks(source_ids):
        rows = db.execute(select(TeachingResource.id, TeachingResource.title, TeachingResource.source_type,
                  TeachingResource.cohort_year, SourceCatalogDetail.institution).outerjoin(
                  SourceCatalogDetail,SourceCatalogDetail.source_id == TeachingResource.id).where(
                  TeachingResource.id.in_(part), TeachingResource.kind=="source"))
        for sid,title,kind,year,school in rows:
            sources.append({"id":sid,"title":title,"type":kind or "","year":year or "","institution":school or ""})
            for field,value in (("source_types",kind),("years",year),("institutions",school)):
                if value:
                    facts[field].add(value)
    return {**{k:sorted(v) for k,v in facts.items()}, "sources":sorted(sources,key=lambda x:x["id"])}
