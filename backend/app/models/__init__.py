from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[int] = mapped_column(BigInteger)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

class StoredFile(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[int] = mapped_column(BigInteger)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, index=True)

class FileReference(Base):
    __tablename__ = "file_references"
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(100), primary_key=True)

class TeachingResource(Base):
    __tablename__ = "teaching_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    solution: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("teaching_resources.id", ondelete="RESTRICT"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    exam_type: Mapped[str] = mapped_column(String(80), default="", server_default="")
    chapter: Mapped[str] = mapped_column(String(120), default="", server_default="")
    question_type: Mapped[str] = mapped_column(String(20), default="", server_default="")
    unit_type: Mapped[str] = mapped_column(String(24), default="", server_default="")
    source_type: Mapped[str] = mapped_column(String(16), default="", server_default="")
    authority_tier: Mapped[str] = mapped_column(String(24), default="", server_default="")
    cohort_year: Mapped[str] = mapped_column(String(12), default="", server_default="")
    series_key: Mapped[str] = mapped_column(String(80), default="", server_default="")
    edition: Mapped[str] = mapped_column(String(60), default="", server_default="")
    dedup_reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    analysis: Mapped[str] = mapped_column(Text, default="", server_default="")
    proof: Mapped[str] = mapped_column(Text, default="", server_default="")
    exams: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sources_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    dedup_override: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    project: Mapped[str] = mapped_column(String(100))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(80))
    attachments: Mapped[list] = mapped_column(JSON)
    resource_refs: Mapped[list] = mapped_column(JSON,default=list)
    intake_intent: Mapped[str | None] = mapped_column(String(16),nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)

class ResourceSourceLink(Base):
    __tablename__ = "resource_source_links"
    resource_id: Mapped[str] = mapped_column(ForeignKey("teaching_resources.id",ondelete="CASCADE"),primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True)
    provenance_role: Mapped[str] = mapped_column(String(16),primary_key=True)
    original_question_number: Mapped[str] = mapped_column(String(40))
    page_start: Mapped[int | None] = mapped_column(Integer,nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer,nullable=True)
    chapter: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(String(300))
    is_primary: Mapped[bool] = mapped_column(Boolean)
    role_verified: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        CheckConstraint("resource_id <> source_id",name="ck_resource_source_not_self"),
        CheckConstraint("provenance_role IN ('original','reproduced','adapted')",name="ck_resource_source_role"),
        CheckConstraint("(page_start IS NULL OR page_start >= 1) AND (page_end IS NULL OR page_end >= 1) AND (page_start IS NULL OR page_end IS NULL OR page_end >= page_start)",name="ck_resource_source_pages"),
    )

class SourceVersion(Base):
    __tablename__ = "resource_source_versions"
    source_id: Mapped[str] = mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True)
    version: Mapped[int] = mapped_column(Integer,primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(BigInteger)

class KnowledgePointCatalog(Base):
    __tablename__ = "knowledge_point_catalog"
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    code: Mapped[str] = mapped_column(String(16),unique=True)
    name: Mapped[str] = mapped_column(String(180))
    name_key: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(40))
    chapter: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    replaced_by_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),nullable=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    __table_args__=(UniqueConstraint("subject","name_key",name="uq_kp_subject_name"),CheckConstraint("status IN ('active','disabled','replaced')",name="ck_kp_status"),CheckConstraint("replaced_by_id IS NULL OR replaced_by_id <> id",name="ck_kp_not_self"))

class ResourceKnowledgeLink(Base):
    __tablename__ = "resource_knowledge_links"
    resource_id: Mapped[str] = mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    __table_args__=(CheckConstraint("role IN ('core','related')",name="ck_resource_kp_role"),)

class KnowledgeAlias(Base):
    __tablename__="knowledge_aliases"
    knowledge_id: Mapped[str]=mapped_column(ForeignKey("knowledge_point_catalog.id",ondelete="CASCADE"),primary_key=True)
    normalized: Mapped[str]=mapped_column(String(180),primary_key=True)
    alias: Mapped[str]=mapped_column(String(180))

class KnowledgeRelation(Base):
    __tablename__="knowledge_relations"
    source_id: Mapped[str]=mapped_column(ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True)
    target_id: Mapped[str]=mapped_column(ForeignKey("knowledge_point_catalog.id",ondelete="RESTRICT"),primary_key=True)
    relation_type: Mapped[str]=mapped_column(String(16),primary_key=True)
    __table_args__=(CheckConstraint("source_id <> target_id",name="ck_knowledge_relation_not_self"),CheckConstraint("relation_type IN ('contains','related','prerequisite')",name="ck_knowledge_relation_type"))

class TeachingDocument(Base):
    __tablename__="teaching_documents"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    title: Mapped[str]=mapped_column(String(200))
    kind: Mapped[str]=mapped_column(String(16))
    subject: Mapped[str]=mapped_column(String(40))
    source_id: Mapped[str | None]=mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),nullable=True)
    blocks: Mapped[list]=mapped_column(JSON)
    revision: Mapped[int]=mapped_column(Integer)
    archived: Mapped[bool]=mapped_column(Boolean)
    created_at: Mapped[int]=mapped_column(BigInteger)
    updated_at: Mapped[int]=mapped_column(BigInteger)

class DocumentAiEdit(Base):
    __tablename__="document_ai_edits"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    document_id: Mapped[str]=mapped_column(ForeignKey("teaching_documents.id",ondelete="RESTRICT"),index=True)
    base_revision: Mapped[int]=mapped_column(Integer)
    base_blocks: Mapped[list]=mapped_column(JSON)
    fields: Mapped[list]=mapped_column(JSON)
    instruction: Mapped[str]=mapped_column(Text)
    model: Mapped[str]=mapped_column(String(80))
    state: Mapped[str]=mapped_column(String(16))
    detail: Mapped[str]=mapped_column(Text)
    changes: Mapped[list]=mapped_column(JSON)
    accepted: Mapped[list]=mapped_column(JSON)
    created_at: Mapped[int]=mapped_column(BigInteger)
    updated_at: Mapped[int]=mapped_column(BigInteger)

class DocumentResourceReference(Base):
    __tablename__="document_resource_refs"
    document_id: Mapped[str]=mapped_column(ForeignKey("teaching_documents.id",ondelete="CASCADE"),primary_key=True)
    resource_id: Mapped[str]=mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),primary_key=True)

class IntakeImport(Base):
    __tablename__="intake_imports"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    file_id: Mapped[str]=mapped_column(ForeignKey("files.id",ondelete="RESTRICT"),index=True)
    text: Mapped[str]=mapped_column(Text)
    metadata_json: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[int]=mapped_column(BigInteger)

class IntakeJob(Base):
    __tablename__="intake_jobs"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    title: Mapped[str]=mapped_column(String(200))
    subject: Mapped[str]=mapped_column(String(40))
    input_text: Mapped[str]=mapped_column(Text)
    provenance: Mapped[dict | None]=mapped_column(JSON,nullable=True)
    source_id: Mapped[str | None]=mapped_column(ForeignKey("teaching_resources.id",ondelete="RESTRICT"),nullable=True,index=True)
    retry_of: Mapped[str | None]=mapped_column(ForeignKey("intake_jobs.id",ondelete="RESTRICT"),nullable=True,unique=True)
    model: Mapped[str]=mapped_column(String(80))
    state: Mapped[str]=mapped_column(String(16))
    detail: Mapped[str]=mapped_column(Text)
    items: Mapped[list]=mapped_column(JSON)
    document_id: Mapped[str | None]=mapped_column(ForeignKey("teaching_documents.id",ondelete="RESTRICT"),nullable=True)
    revision: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[int]=mapped_column(BigInteger)
    updated_at: Mapped[int]=mapped_column(BigInteger)

class IntakeSupplement(Base):
    __tablename__="intake_supplements"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    job_id: Mapped[str]=mapped_column(ForeignKey("intake_jobs.id",ondelete="RESTRICT"),index=True)
    item_uid: Mapped[str]=mapped_column(String(36))
    base_revision: Mapped[int]=mapped_column(Integer)
    base_item: Mapped[dict]=mapped_column(JSON)
    fields: Mapped[list]=mapped_column(JSON)
    instruction: Mapped[str]=mapped_column(Text)
    model: Mapped[str]=mapped_column(String(80))
    state: Mapped[str]=mapped_column(String(16))
    detail: Mapped[str]=mapped_column(Text)
    proposal: Mapped[dict]=mapped_column(JSON)
    accepted: Mapped[list]=mapped_column(JSON)
    created_at: Mapped[int]=mapped_column(BigInteger)
    updated_at: Mapped[int]=mapped_column(BigInteger)

class StudioItem(Base):
    __tablename__="studio_items"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    kind: Mapped[str]=mapped_column(String(24),index=True)
    title: Mapped[str]=mapped_column(String(200))
    data: Mapped[dict]=mapped_column(JSON)
    revision: Mapped[int]=mapped_column(Integer)
    archived: Mapped[bool]=mapped_column(Boolean)
    created_at: Mapped[int]=mapped_column(BigInteger)
    updated_at: Mapped[int]=mapped_column(BigInteger)

class StudioRevision(Base):
    __tablename__="studio_revisions"
    item_id: Mapped[str]=mapped_column(ForeignKey("studio_items.id",ondelete="RESTRICT"),primary_key=True)
    revision: Mapped[int]=mapped_column(Integer,primary_key=True)
    snapshot: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[int]=mapped_column(BigInteger)

class VideoProject(Base):
    __tablename__ = "video_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("teaching_resources.id", ondelete="RESTRICT"))
    resource_revision: Mapped[int] = mapped_column(Integer)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    engine_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    work_id: Mapped[str | None] = mapped_column(ForeignKey("studio_items.id", ondelete="RESTRICT"), nullable=True, unique=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint("resource_id", "resource_revision", name="uq_video_resource_revision"),)
