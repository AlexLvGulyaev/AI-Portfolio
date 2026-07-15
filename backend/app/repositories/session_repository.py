"""
Repository for chat sessions.

Based on Assistant Flow (repositories/session_repository.py).
"""

from uuid import UUID
from typing import Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.entities import ChatSession, ChatMessage


class SessionRepository:
    """Repository for chat sessions and messages."""

    def create_session(
        self,
        db: Session,
        user_id: UUID | None,
        *,
        mode: str = "text",
        is_active: bool = True,
    ) -> UUID:
        """Create a new chat session."""
        session = ChatSession(
            user_id=user_id,
            mode=mode,
            is_active=is_active,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id

    def get_session_by_id(self, db: Session, session_id: UUID) -> dict[str, Any] | None:
        """Get session by ID."""
        session = db.scalars(
            select(ChatSession).where(ChatSession.id == session_id).limit(1)
        ).first()
        if not session:
            return None
        return {
            "id": session.id,
            "user_id": session.user_id,
            "mode": session.mode,
            "is_active": session.is_active,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def get_active_session_for_user(self, db: Session, user_id: UUID | None) -> dict[str, Any] | None:
        """Get active session for user."""
        session = db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .where(ChatSession.is_active == True)
            .order_by(ChatSession.created_at.desc())
            .limit(1)
        ).first()
        if not session:
            return None
        return {
            "id": session.id,
            "user_id": session.user_id,
            "mode": session.mode,
            "is_active": session.is_active,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def set_session_mode(self, db: Session, session_id: UUID, mode: str) -> None:
        """Set session mode."""
        db.scalars(
            select(ChatSession).where(ChatSession.id == session_id)
        ).first().mode = mode
        db.commit()

    def deactivate_all_active_for_user(self, db: Session, user_id: UUID | None) -> None:
        """Deactivate all active sessions for user."""
        db.query(ChatSession).filter(
            ChatSession.user_id == user_id,
            ChatSession.is_active == True
        ).update({"is_active": False})
        db.commit()

    def append_message(
        self,
        db: Session,
        session_id: UUID,
        user_id: UUID | None,
        *,
        role: str,
        content: str,
        modality: str = "text",
        metadata: dict[str, Any] | None = None,
        execution_id: str | None = None,
        intake_event_id: UUID | None = None,
    ) -> UUID:
        """Append message to session."""
        message = ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            message_metadata=metadata,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message.id

    def list_messages_for_session(
        self, db: Session, session_id: UUID, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List messages for session (newest first)."""
        messages = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": str(msg.id),
                "session_id": str(msg.session_id),
                "user_id": str(msg.user_id) if msg.user_id else None,
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.message_metadata or {},
                "created_at": msg.created_at,
                "execution_id": None,
                "intake_event_id": None,
            }
            for msg in messages
        ]