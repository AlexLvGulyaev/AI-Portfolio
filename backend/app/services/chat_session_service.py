"""
Chat Session Service for AI Portfolio.

Source: Assistant Flow (services/chat_session_service.py)
Adapted for AI Portfolio (uses visitor_id instead of Telegram user_id).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.session_repository import SessionRepository


class ChatSessionService:
    """
    Coordination of sessions and messages in PostgreSQL.

    Source: Assistant Flow (ChatSessionService)
    Adapted for AI Portfolio:
    - Uses visitor_id instead of Telegram user_id
    - Simplified for public portfolio use case
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repository = SessionRepository()

    def get_or_create_active_session(
        self, visitor_id: str | None, *, mode: str = "text"
    ) -> uuid.UUID:
        """
        Get active session for visitor or create new one.

        Args:
            visitor_id: Visitor ID (from cookie or None for anonymous)
            mode: Session mode ('text' by default)

        Returns:
            Session ID
        """
        uid = uuid.UUID(str(visitor_id)) if visitor_id else None

        row = self._repository.get_active_session_for_user(self._db, uid)
        if row:
            return row["id"]

        return self._repository.create_session(self._db, uid, mode=mode, is_active=True)

    def create_session(
        self, visitor_id: str | None, *, mode: str = "text"
    ) -> uuid.UUID:
        """
        Create new session.

        Args:
            visitor_id: Visitor ID (from cookie or None for anonymous)
            mode: Session mode ('text' by default)

        Returns:
            Session ID
        """
        uid = uuid.UUID(str(visitor_id)) if visitor_id else None
        return self._repository.create_session(self._db, uid, mode=mode, is_active=True)

    def get_session_by_id(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        """
        Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session dict or None if not found
        """
        return self._repository.get_session_by_id(self._db, session_id)

    def set_mode(self, session_id: uuid.UUID, mode: str) -> None:
        """Set session mode."""
        self._repository.set_session_mode(self._db, session_id, mode)

    def close_session(self, session_id: uuid.UUID) -> None:
        """
        Close session (deactivate).

        Args:
            session_id: Session ID to close
        """
        from app.models.entities import ChatSession
        from sqlalchemy import update

        self._db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(is_active=False)
        )
        self._db.commit()

    def record_message(
        self,
        session_id: uuid.UUID,
        visitor_id: str | None,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """
        Append message to session.

        Args:
            session_id: Session ID
            visitor_id: Visitor ID (from cookie or None for anonymous)
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata

        Returns:
            Message ID
        """
        uid = uuid.UUID(str(visitor_id)) if visitor_id else None
        return self._repository.append_message(
            self._db,
            session_id,
            uid,
            role=role,
            content=content,
            metadata=metadata,
        )

    def list_recent_messages_raw(
        self, session_id: uuid.UUID, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Get raw message rows (newest first).

        Args:
            session_id: Session ID
            limit: Maximum number of messages

        Returns:
            List of message dictionaries
        """
        return self._repository.list_messages_for_session(
            self._db, session_id, limit=limit
        )

    def rotate_active_session(
        self, visitor_id: str | None, *, mode: str = "text"
    ) -> uuid.UUID:
        """
        Deactivate all active sessions for visitor and create new one.

        Args:
            visitor_id: Visitor ID (from cookie or None for anonymous)
            mode: Session mode ('text' by default)

        Returns:
            New session ID
        """
        uid = uuid.UUID(str(visitor_id)) if visitor_id else None

        self._repository.deactivate_all_active_for_user(self._db, uid)
        return self._repository.create_session(self._db, uid, mode=mode, is_active=True)