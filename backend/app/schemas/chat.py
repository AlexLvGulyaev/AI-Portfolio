"""Pydantic schemas for Chat operations."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class ChatMessageBase(BaseModel):
    """Base schema for Chat Message."""

    role: str
    content: str


class ChatMessageOut(ChatMessageBase):
    """Output schema for Chat Message."""

    id: UUID
    session_id: UUID
    user_id: UUID | None = None
    created_at: datetime
    metadata: dict | None = None

    class Config:
        from_attributes = True


class ChatSessionBase(BaseModel):
    """Base schema for Chat Session."""

    user_id: UUID | None = None
    mode: str = "text"


class ChatSessionOut(ChatSessionBase):
    """Output schema for Chat Session."""

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Chat request from user."""

    message: str
    session_id: UUID | None = None


class ChatResponse(BaseModel):
    """Chat response from AI."""

    answer: str
    session_id: UUID
    sources: list[str] = []
    provider: str
    model: str = ""
    from_cache: bool = False
    rag_used: bool = False
    response_time_ms: int
    user_id: UUID | None = None