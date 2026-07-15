"""
Logs / Conversations service for admin console.

Lists operational logs with filtering and chat sessions with pagination.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, ChatSession, OperationalLog


class LogsConversationsService:
    """Admin Logs and Conversations service."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Operational logs
    # ------------------------------------------------------------------

    def list_logs(
        self,
        *,
        event_type: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return filtered operational logs with pagination."""
        query = select(OperationalLog).order_by(desc(OperationalLog.created_at))

        if event_type:
            query = query.where(OperationalLog.event_type == event_type)
        if status:
            query = query.where(OperationalLog.status == status)
        if date_from:
            start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            query = query.where(OperationalLog.created_at >= start)
        if date_to:
            end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
            query = query.where(OperationalLog.created_at <= end)

        total = self._db.scalar(select(func.count()).select_from(query.subquery()))

        rows = self._db.scalars(query.limit(limit).offset(offset)).all()

        return {
            "items": [self._log_to_dict(row) for row in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def list_conversations(
        self,
        *,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return chat sessions with pagination."""
        query = select(ChatSession).order_by(desc(ChatSession.created_at))

        if is_active is not None:
            query = query.where(ChatSession.is_active.is_(is_active))

        total = self._db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._db.scalars(query.limit(limit).offset(offset)).all()

        return {
            "items": [self._conversation_to_dict(row) for row in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }

    def get_conversation(self, session_id: UUID) -> dict[str, Any]:
        """Return chat session details with messages."""
        session = self._db.get(ChatSession, session_id)
        if not session:
            raise HTTPException(404, "Conversation not found")

        message_count = self._db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
        )

        messages = self._db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        ).all()

        return {
            **self._conversation_to_dict(session),
            "message_count": message_count or 0,
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_to_dict(self, row: OperationalLog) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "event_type": row.event_type,
            "session_id": str(row.session_id) if row.session_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "source": row.source,
            "query": row.query,
            "response": row.response,
            "model_name": row.model_name,
            "provider_key": row.provider_key,
            "from_cache": row.from_cache,
            "response_time_ms": row.response_time_ms,
            "status": row.status,
            "error_message": row.error_message,
            "metadata": row.log_metadata or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _conversation_to_dict(self, row: ChatSession) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else None,
            "mode": row.mode,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
