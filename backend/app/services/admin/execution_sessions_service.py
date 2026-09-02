"""
Admin service for execution sessions and step-level tracing.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import desc, func, select, String as sa_String
from sqlalchemy.orm import Session

from app.models.entities import ExecutionSession, ExecutionStep


class ExecutionSessionsAdminService:
    """Service for listing and inspecting execution sessions."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_sessions(
        self,
        *,
        route: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return paginated execution sessions with optional filters."""
        query = select(ExecutionSession).order_by(desc(ExecutionSession.created_at))

        if route:
            query = query.where(ExecutionSession.route == route)
        if status:
            query = query.where(ExecutionSession.status == status)
        if date_from:
            start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            query = query.where(ExecutionSession.created_at >= start)
        if date_to:
            end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
            query = query.where(ExecutionSession.created_at <= end)
        if search:
            search_lower = f"%{search.lower()}%"
            query = query.where(
                func.lower(ExecutionSession.provider_key).like(search_lower)
                | func.lower(ExecutionSession.model_name).like(search_lower)
                | func.lower(ExecutionSession.event_type).like(search_lower)
                | func.lower(ExecutionSession.client_ip).like(search_lower)
                | func.cast(ExecutionSession.visitor_id, sa_String).like(search_lower)
                # текст вопроса/ответа/источников лежит в JSON-метаданных —
                # ищем по нему как по тексту (запрос «CRM» находит диалоги о CRM)
                | func.lower(
                    func.cast(ExecutionSession.execution_metadata, sa_String)
                ).like(search_lower)
            )

        total = self._db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._db.scalars(query.limit(limit).offset(offset)).all()

        return {
            "items": [self._session_to_dict(row) for row in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }

    def get_session(self, execution_id: UUID) -> dict[str, Any]:
        """Return execution session with its steps and linked operational log."""
        session = self._db.get(ExecutionSession, execution_id)
        if not session:
            raise HTTPException(404, "Execution session not found")

        steps = self._db.scalars(
            select(ExecutionStep)
            .where(ExecutionStep.execution_session_id == execution_id)
            .order_by(ExecutionStep.step_order, ExecutionStep.created_at)
        ).all()

        result = self._session_to_dict(session)
        result["steps"] = [self._step_to_dict(step) for step in steps]
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _session_to_dict(self, row: ExecutionSession) -> dict[str, Any]:
        metadata = row.execution_metadata or {}
        return {
            "id": str(row.id),
            "session_id": str(row.session_id) if row.session_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "visitor_id": str(row.visitor_id) if row.visitor_id else None,
            "client_ip": row.client_ip,
            "user_agent": row.user_agent,
            "event_type": row.event_type,
            "route": row.route,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "duration_ms": row.duration_ms,
            "provider_key": row.provider_key,
            "model_name": row.model_name,
            "metadata": metadata,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "is_backfilled": bool(row.is_backfilled),
        }

    def _step_to_dict(self, row: ExecutionStep) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "execution_session_id": str(row.execution_session_id),
            "stage_name": row.stage_name,
            "step_order": row.step_order,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "duration_ms": row.duration_ms,
            "metadata": row.step_metadata or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

