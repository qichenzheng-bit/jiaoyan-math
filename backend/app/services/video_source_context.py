"""Capture provenance from actual question/source records, never from guessed title text."""
from sqlalchemy import select
from app.models import TeachingResource, ResourceSourceLink, SourceCatalogDetail, KnowledgePointCatalog, ResourceKnowledgeLink

def source_entry(link, source, detail):
    occurrences = link.occurrences or []
    numbers = {str(o.get("original_question_number") or "").strip() for o in occurrences if isinstance(o, dict)}
    numbers.discard("")
    # Multiple positions in a source can be ambiguous. Never select a guessed question number.
    number = (next(iter(numbers)) if len(numbers) == 1 else "") if occurrences else (link.original_question_number or "")
    return {
        "source_name": source.title or "", "year": source.cohort_year or "",
        "institution": detail.institution if detail else "",
        "exam_type": source.exam_type or "", "source_type": source.source_type or "",
        "source_subject": source.subject or "", "question_number": number,
        "provenance_role": link.provenance_role, "role_verified": bool(link.role_verified),
        "is_primary": bool(link.is_primary),
    }

def select_opening_source(sources):
    originals = [s for s in sources if s["provenance_role"] == "original" and s["role_verified"]]
    primary = [s for s in originals if s["is_primary"]]
    if len(primary) == 1:
        return primary[0]
    if len(originals) == 1:
        return originals[0]
    if originals:
        return None
    primary = [s for s in sources if s["is_primary"]]
    if len(primary) == 1:
        return primary[0]
    return sources[0] if len(sources) == 1 else None

def capture(db, resource):
    rows = db.execute(select(ResourceSourceLink, TeachingResource, SourceCatalogDetail)
        .select_from(ResourceSourceLink)
        .join(TeachingResource, TeachingResource.id == ResourceSourceLink.source_id)
        .outerjoin(SourceCatalogDetail, SourceCatalogDetail.source_id == TeachingResource.id)
        .where(ResourceSourceLink.resource_id == resource.id, TeachingResource.kind == "source")
        .order_by(ResourceSourceLink.source_id, ResourceSourceLink.provenance_role)).all()
    sources = [source_entry(link, source, detail) for link, source, detail in rows]
    tags = db.execute(select(KnowledgePointCatalog.name, ResourceKnowledgeLink.role)
        .select_from(KnowledgePointCatalog)
        .join(ResourceKnowledgeLink, ResourceKnowledgeLink.knowledge_id == KnowledgePointCatalog.id)
        .where(ResourceKnowledgeLink.resource_id == resource.id)
        .order_by(ResourceKnowledgeLink.role, KnowledgePointCatalog.name)).all()
    return {"opening_source": select_opening_source(sources),
            "knowledge_tags": [{"name": name, "role": role} for name, role in tags],
            "source_count": len(sources)}
