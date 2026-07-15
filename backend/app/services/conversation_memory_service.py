"""
Conversation Memory Service for AI Portfolio.

Source: Assistant Flow (services/memory/conversation_memory_service.py)
Adapted for AI Portfolio (removed security context, simplified for public access).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.session_repository import SessionRepository
from app.services.memory.base import (
    ConversationMemoryRecord,
    MemoryBudgetPolicy,
)


def _trim(s: str, max_chars: int) -> str:
    """Trim string to max_chars."""
    if max_chars <= 0:
        return ""
    t = s or ""
    return t if len(t) <= max_chars else t[:max_chars]


def _row_to_record(row: dict[str, Any]) -> ConversationMemoryRecord:
    """Convert database row to ConversationMemoryRecord."""
    md = row.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    return ConversationMemoryRecord(
        message_id=str(row["id"]),
        session_id=str(row["session_id"]),
        user_id=str(row["user_id"]) if row.get("user_id") else "",
        role=str(row["role"]),
        content=str(row.get("content") or ""),
        created_at=row["created_at"],
        metadata=dict(md),
        execution_id=str(row["execution_id"]) if row.get("execution_id") else None,
    )


class ConversationMemoryService:
    """
    Read/write dialog history: budget discipline, stable ordering.

    Source: Assistant Flow (ConversationMemoryService)
    Adapted for AI Portfolio:
    - Removed security context (public access)
    - Uses visitor_id instead of Telegram user_id
    - Simplified for portfolio use case
    """

    def __init__(
        self,
        *,
        db: Session,
        policy: MemoryBudgetPolicy | None = None,
    ) -> None:
        self._db = db
        self._sessions = SessionRepository()
        self._policy = policy or MemoryBudgetPolicy()

    def get_recent_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        """Get recent messages for session."""
        return self._load_budgeted(session_id, limit=limit)

    def get_session_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        """Alias for get_recent_messages (explicit API)."""
        return self._load_budgeted(session_id, limit=limit)

    def _load_budgeted(self, session_id: str, *, limit: int) -> list[ConversationMemoryRecord]:
        """Load messages with budget policy applied."""
        t0 = time.monotonic()
        sid = uuid.UUID(str(session_id))
        fetch_limit = max(1, min(int(limit), self._policy.max_recent_messages, 500))
        raw = self._sessions.list_messages_for_session(self._db, sid, limit=fetch_limit)

        # raw: newest first; return chronological after reverse
        budget_applied = False
        picked: list[dict[str, Any]] = []
        total_chars = 0
        max_msg = self._policy.max_message_chars
        budget = max(0, int(self._policy.total_memory_chars_budget))

        for row in raw:
            c = _trim(str(row.get("content") or ""), max_msg)
            room = budget - total_chars
            if room <= 0:
                if picked:
                    budget_applied = True
                break
            if len(c) > room:
                budget_applied = True
                c = c[:room]
            row = {**row, "content": c}
            picked.append(row)
            total_chars += len(c)

        picked.reverse()
        records = [_row_to_record(r) for r in picked]

        return records

    def add_message(
        self,
        session_id: str,
        user_id: str | None,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Add message to conversation history.

        Args:
            session_id: Session ID
            user_id: Visitor ID (optional)
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata

        Returns:
            Message ID
        """
        sid = uuid.UUID(str(session_id))
        uid = uuid.UUID(str(user_id)) if user_id else None

        message_id = self._sessions.append_message(
            self._db,
            sid,
            uid,
            role=role,
            content=content,
            metadata=metadata or {},
        )

        return str(message_id)