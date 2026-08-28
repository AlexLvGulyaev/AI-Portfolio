"""
SQLAlchemy models for AI Portfolio Backend.

Based on:
- Review Flow: AIProviderSetting, OperationalLog
- Assistant Flow: ChatSession, ChatMessage
- PEcf09: Logging structure (user_id, source, query, response, from_cache, response_time_ms)
"""

from datetime import datetime
from uuid import uuid4, UUID as UUIDType
from sqlalchemy import Column, String, Boolean, Integer, Float, Text, DateTime, ForeignKey, JSON, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ProjectCard(Base):
    """
    Managed project card for public portfolio catalog.

    Source of Truth for project cards in the public frontend.
    Public frontend receives cards through read-only backend API.
    """

    __tablename__ = "project_cards"

    __table_args__ = (
        CheckConstraint(
            "show_on_homepage BETWEEN 0 AND 4",
            name="ck_project_cards_show_on_homepage_range",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    short_description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, default="cases")
    tags = Column(JSON, default=list)
    display_order = Column(Integer, default=0, nullable=False)
    show_on_homepage = Column(Integer, default=0, nullable=False)
    is_visible = Column(Boolean, default=True, nullable=False)
    knowledge_content = Column(Text)
    external_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeSource(Base):
    """
    Knowledge Base source for manual synchronization into ChromaDB.

    ChromaDB is a search index, not a Source of Truth.
    """

    __tablename__ = "knowledge_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_type = Column(String(50), nullable=False)  # github_repo / local_directory / local_file
    identifier = Column(String(500), nullable=False)  # owner/repo or path
    display_name = Column(String(200))  # human-readable project name (Admission Console)
    branch = Column(String(100), default="main")
    base_path = Column(String(500))
    is_enabled = Column(Boolean, default=True, nullable=False)
    # KB admission gate (fail-closed): only "approved" sources are indexed.
    admission_status = Column(String(20), nullable=False, default="pending", server_default="pending")  # pending / approved / blocked
    include_patterns = Column(JSON, default=list)  # EFFECTIVE allowlist consumed by sync; changed only by approval
    exclude_patterns = Column(JSON, default=list)  # EFFECTIVE deny globs; take priority over include_patterns
    # Draft patterns (Admission Console working copy). NULL means the draft
    # equals the effective patterns. Draft edits and previews NEVER touch the
    # effective patterns — the previously approved composition stays in force
    # until a new approval.
    draft_include_patterns = Column(JSON)
    draft_exclude_patterns = Column(JSON)
    # Approval of an immutable admission preview (Admission Console).
    approved_preview_id = Column(UUID(as_uuid=True))  # no DB-level FK: table created in the same migration
    approved_at = Column(DateTime)
    last_sync_at = Column(DateTime)
    last_sync_status = Column(String(50), default="pending")  # pending / success / error
    last_sync_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KBAdmissionPreview(Base):
    """
    Immutable admission-preview artifact for a knowledge source.

    Built from the source's DRAFT patterns at creation time; never mutated
    afterwards. Approval references a preview id — the approved composition
    (patterns + commit SHA) is fixed by this row.
    """

    __tablename__ = "kb_admission_previews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="ready")  # ready / error
    commit_sha = Column(String(100))  # repository head commit at preview time (None on error)
    include_patterns = Column(JSON)
    exclude_patterns = Column(JSON)
    candidates_total = Column(Integer, default=0)
    included_count = Column(Integer, default=0)
    excluded_count = Column(Integer, default=0)
    files = Column(JSON)  # [{path, decision, reason, pattern}]
    error_code = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class KBAdmissionEvent(Base):
    """
    Admission decision history event for a knowledge source (audit log).
    """

    __tablename__ = "kb_admission_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # created / preview_created / approved / blocked / unblocked / draft_updated / draft_reset / approval_rejected
    summary = Column(String(500))
    details = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeDocument(Base):
    """
    Cached raw documents fetched from KB sources (GitHub, local).

    Intermediate storage before chunking and indexing into ChromaDB.
    """

    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    path = Column(String(500), nullable=False)
    title = Column(String(500))
    content = Column(Text)
    raw_url = Column(String(1000))
    commit_sha = Column(String(100))
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeSyncError(Base):
    """
    Per-source sync error log.
    """

    __tablename__ = "knowledge_sync_errors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_sources.id"), nullable=False, index=True)
    path = Column(String(500))
    error_type = Column(String(100))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeSyncJob(Base):
    """
    Knowledge Base synchronization job history.
    """

    __tablename__ = "knowledge_sync_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    triggered_by = Column(String(50), nullable=False, default="manual")  # manual / future_scheduler
    status = Column(String(50), nullable=False, default="pending")  # pending / running / success / error
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    stats = Column(JSON, default=dict)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIProviderSetting(Base):
    """
    AI Provider settings.

    Source: Review Flow (ai_provider_settings)
    Allows runtime switching between providers.
    """

    __tablename__ = "ai_provider_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_key = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100))
    model_name = Column(String(100))
    is_enabled = Column(Boolean, default=True)
    is_active = Column(Boolean, default=False)
    is_fallback = Column(Boolean, default=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=500)
    api_key_env_key = Column(String(100))
    base_url_env_key = Column(String(100))
    base_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    """
    Chat session for conversation memory.

    Source: Assistant Flow (chat_sessions)
    Tracks conversation sessions with users.
    """

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), index=True)  # visitor_id from cookie
    mode = Column(String(20), default="text")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    """
    Chat message history.

    Source: Assistant Flow (chat_messages)
    Required fields from PEcf09, Assistant Flow: session_id, user_id, role, content
    """

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), index=True)  # visitor_id from PEcf09, Assistant Flow
    role = Column(String(20), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON)  # renamed from 'metadata' (reserved in SQLAlchemy)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ExecutionSession(Base):
    """
    Execution tracing session for a single request through ChatOrchestrator.

    One execution session corresponds to one pass of ChatOrchestrator.process_request.
    Stores the full pipeline trace plus visitor/client context for observability.
    """

    __tablename__ = "execution_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    visitor_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    client_ip = Column(String(100), nullable=True)
    user_agent = Column(Text, nullable=True)
    event_type = Column(String(100), nullable=False, default="chat_request")
    route = Column(String(50), nullable=False, default="text")  # text | rag | log | image | audio
    status = Column(String(20), nullable=False, default="ok")  # ok | error
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    provider_key = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    execution_metadata = Column(JSON, default=dict)  # renamed from 'metadata' (reserved in SQLAlchemy)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_backfilled = Column(Boolean, default=False, nullable=False)


class ExecutionStep(Base):
    """
    Step-level trace inside an ExecutionSession.

    Captures pipeline stages such as session_resolve, memory_load, rag_search, llm_call, etc.
    """

    __tablename__ = "execution_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="ok")  # ok | error | skipped | running
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    step_metadata = Column(JSON, default=dict)  # renamed from 'metadata' (reserved in SQLAlchemy)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OperationalLog(Base):
    """
    Operational logging for AI interactions.

    Source: PEcf09, Assistant Flow, Review Flow
    Required fields:
    - PEcf09: user_id, source, query, response, from_cache, response_time_ms
    - Assistant Flow: session_id, metadata
    - Review Flow: event_type, model_name, latency_ms, status
    """

    __tablename__ = "operational_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type = Column(String(100), nullable=False, index=True)  # From Review Flow
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id = Column(UUID(as_uuid=True), index=True)  # From Assistant Flow
    user_id = Column(UUID(as_uuid=True), index=True)  # From PEcf09, Assistant Flow
    source = Column(String(20))  # From PEcf09: 'web', 'api'
    query = Column(Text)  # From PEcf09
    response = Column(Text)  # From PEcf09
    model_name = Column(String(100))  # From Review Flow
    provider_key = Column(String(50), index=True)  # For AI Portfolio
    from_cache = Column(Boolean)  # From PEcf09
    response_time_ms = Column(Integer)  # From PEcf09
    status = Column(String(20), index=True)  # From Review Flow
    error_message = Column(Text)  # From Review Flow
    log_metadata = Column(JSON)  # From Assistant Flow (renamed from 'metadata')
    created_at = Column(DateTime, default=datetime.utcnow, index=True)