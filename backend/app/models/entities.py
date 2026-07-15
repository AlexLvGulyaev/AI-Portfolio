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
    branch = Column(String(100))
    base_path = Column(String(500))
    is_enabled = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime)
    last_sync_status = Column(String(50), default="pending")  # pending / success / error
    last_sync_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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