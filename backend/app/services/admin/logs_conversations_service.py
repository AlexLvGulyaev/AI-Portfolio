"""
Logs / Conversations service for admin console.

Lists operational logs with filtering and chat sessions with pagination.
Conversations view adapted from Assistant Flow Memory Console:
- session list with last-execution runtime context,
- detail panel with paired dialog turns, execution timeline and memory budget.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func, desc, cast, String, or_, and_
from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, ChatSession, ExecutionSession, ExecutionStep, OperationalLog
from app.services.memory.base import MemoryBudgetPolicy


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
        hours: int | None = None,
        route: str | None = None,
        active_only: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return chat sessions with pagination and runtime context."""
        query = select(ChatSession).order_by(desc(ChatSession.updated_at))

        if hours is not None and hours > 0:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            query = query.where(ChatSession.updated_at >= cutoff)

        if active_only is not None:
            query = query.where(ChatSession.is_active.is_(active_only))

        # Filter by route of the *latest* execution session for this chat session.
        if route and route != "all":
            latest_execution_subq = (
                select(
                    ExecutionSession.session_id.label("session_id"),
                    func.max(ExecutionSession.created_at).label("max_created"),
                )
                .group_by(ExecutionSession.session_id)
                .subquery("latest_execution")
            )
            query = query.join(
                latest_execution_subq,
                latest_execution_subq.c.session_id == ChatSession.id,
            ).join(
                ExecutionSession,
                and_(
                    ExecutionSession.session_id == latest_execution_subq.c.session_id,
                    ExecutionSession.created_at == latest_execution_subq.c.max_created,
                ),
            ).where(ExecutionSession.route == route)

        if search:
            q = f"%{search}%"
            query = query.where(
                or_(
                    cast(ChatSession.id, String).ilike(q),
                    cast(ChatSession.user_id, String).ilike(q),
                    cast(ChatSession.mode, String).ilike(q),
                )
            )

        total = self._db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._db.scalars(query.limit(limit).offset(offset)).all()

        return {
            "items": [self._conversation_to_dict(row) for row in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }

    def get_conversation(self, session_id: UUID) -> dict[str, Any]:
        """Return chat session details with messages, turns, executions and budget."""
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
            .limit(500)
        ).all()

        executions = self._db.scalars(
            select(ExecutionSession)
            .where(ExecutionSession.session_id == session_id)
            .order_by(desc(ExecutionSession.started_at))
            .limit(20)
        ).all()

        recent_turns = self._build_recent_turns(messages)

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
            "recent_turns": recent_turns,
            "executions": [self._execution_to_dict(ex) for ex in executions],
            "budget": {
                "max_recent_messages": MemoryBudgetPolicy.max_recent_messages,
                "max_message_chars": MemoryBudgetPolicy.max_message_chars,
                "total_memory_chars_budget": MemoryBudgetPolicy.total_memory_chars_budget,
            },
            "memory_source": "PostgreSQL",
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
        message_count = self._db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.session_id == row.id)
        )
        last_ex = self._get_last_execution_summary(row.id)
        return {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else None,
            "visitor_id": str(row.user_id) if row.user_id else None,
            "mode": row.mode,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "message_count": message_count or 0,
            "turns_approx": round((message_count or 0) / 2.0, 1) if message_count else 0,
            "last_execution": last_ex,
        }

    def _get_last_execution_summary(self, session_id: UUID) -> dict[str, Any] | None:
        ex = self._db.scalars(
            select(ExecutionSession)
            .where(ExecutionSession.session_id == session_id)
            .order_by(desc(ExecutionSession.started_at))
            .limit(1)
        ).first()
        if not ex:
            return None

        log = self._db.scalars(
            select(OperationalLog)
            .where(OperationalLog.execution_id == ex.id)
            .order_by(desc(OperationalLog.created_at))
            .limit(1)
        ).first()

        meta = ex.execution_metadata or {}
        return {
            "id": str(ex.id),
            "route": ex.route,
            "status": ex.status,
            "provider_key": ex.provider_key,
            "model_name": ex.model_name,
            "client_ip": ex.client_ip,
            "response_time_ms": ex.duration_ms or meta.get("response_time_ms"),
            "cache_hit": log.from_cache if log else meta.get("from_cache"),
            "rag_used": ex.route == "rag" or bool(meta.get("rag_used")),
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "finished_at": ex.finished_at.isoformat() if ex.finished_at else None,
        }

    def _execution_to_dict(self, ex: ExecutionSession) -> dict[str, Any]:
        steps = self._db.scalars(
            select(ExecutionStep)
            .where(ExecutionStep.execution_session_id == ex.id)
            .order_by(ExecutionStep.step_order.asc())
        ).all()
        return {
            "id": str(ex.id),
            "session_id": str(ex.session_id) if ex.session_id else None,
            "user_id": str(ex.user_id) if ex.user_id else None,
            "visitor_id": str(ex.visitor_id) if ex.visitor_id else None,
            "client_ip": ex.client_ip,
            "user_agent": ex.user_agent,
            "event_type": ex.event_type,
            "route": ex.route,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "finished_at": ex.finished_at.isoformat() if ex.finished_at else None,
            "duration_ms": ex.duration_ms,
            "provider_key": ex.provider_key,
            "model_name": ex.model_name,
            "metadata": ex.execution_metadata or {},
            "is_backfilled": ex.is_backfilled,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
            "steps": [self._execution_step_to_dict(step) for step in steps],
        }

    def _execution_step_to_dict(self, step: ExecutionStep) -> dict[str, Any]:
        return {
            "id": str(step.id),
            "execution_session_id": str(step.execution_session_id),
            "stage_name": step.stage_name,
            "step_order": step.step_order,
            "status": step.status,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            "duration_ms": step.duration_ms,
            "metadata": step.step_metadata or {},
            "created_at": step.created_at.isoformat() if step.created_at else None,
        }

    @staticmethod
    def _build_recent_turns(messages: list[ChatMessage]) -> list[dict[str, str]]:
        """Pair user/assistant messages chronologically for the dialog table."""
        rows: list[dict[str, str]] = []
        pending_user: str | None = None
        for msg in messages:
            role = (msg.role or "").strip().lower()
            preview = (msg.content or "").strip()
            if role == "user":
                if pending_user is not None:
                    rows.append({"user": pending_user, "assistant": "—"})
                pending_user = preview
            elif role == "assistant":
                rows.append({"user": pending_user or "—", "assistant": preview})
                pending_user = None
        if pending_user is not None:
            rows.append({"user": pending_user, "assistant": "—"})
        return rows
