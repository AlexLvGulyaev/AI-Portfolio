"""
Admin service for recent processing-style logs.

Builds a flat rows view from execution_sessions + execution_steps + operational_logs
so the frontend can group them into execution-session views similar to Assistant Flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import ExecutionSession, ExecutionStep, OperationalLog


_LOG_CAP = 2000

# Preserved detail keys for the admin UI; heavy/unnecessary fields are dropped.
_PRESERVED_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "query",
        "response",
        "session_id",
        "cache_hit",
        "rag_used",
        "sources",
        "sources_count",
        "message_count",
        "from_cache",
        "provider",
        "model",
        "latency_ms",
        "response_time_ms",
        "log_id",
        "fallback_used",
        "fallback_at_select",
        "retry",
        "reason",
        "error",
        "messages_count",
    }
)


class LogsAdminService:
    """Read-only service for /api/admin/logs/recent."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_recent_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        since_hours: int | None = None,
    ) -> dict[str, Any]:
        """Return flat log rows grouped from execution_sessions + steps + operational_logs."""
        limit = max(1, min(int(limit), _LOG_CAP))
        offset = max(0, int(offset))

        session_query = self._db.query(ExecutionSession).order_by(
            ExecutionSession.created_at.desc()
        )
        if since_hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(since_hours)))
            session_query = session_query.where(ExecutionSession.created_at >= cutoff)

        total = session_query.count()
        sessions = session_query.offset(offset).limit(limit).all()
        session_ids = [s.id for s in sessions]

        steps: dict[uuid.UUID, list[ExecutionStep]] = {}
        logs: dict[uuid.UUID, OperationalLog] = {}

        if session_ids:
            step_rows = (
                self._db.query(ExecutionStep)
                .where(ExecutionStep.execution_session_id.in_(session_ids))
                .order_by(ExecutionStep.step_order, ExecutionStep.created_at)
                .all()
            )
            for step in step_rows:
                steps.setdefault(step.execution_session_id, []).append(step)

            log_rows = (
                self._db.query(OperationalLog)
                .where(OperationalLog.execution_id.in_(session_ids))
                .all()
            )
            for log in log_rows:
                logs[log.execution_id] = log

        items: list[dict[str, Any]] = []
        for session in sessions:
            items.extend(self._session_rows(session, steps.get(session.id, []), logs.get(session.id)))

        return {
            "limit": limit,
            "offset": offset,
            "count": len(items),
            "total_sessions": total,
            "items": items,
        }

    def _session_rows(
        self,
        session: ExecutionSession,
        steps: list[ExecutionStep],
        log: OperationalLog | None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        route = session.route or "text"
        provider = session.provider_key or (log.provider_key if log else None)
        model = session.model_name or (log.model_name if log else None)
        query = log.query if log else None
        response = log.response if log else None
        error_text = log.error_message if log else None

        base_meta = {
            "session_id": str(session.session_id) if session.session_id else None,
            "user_id": str(session.user_id) if session.user_id else None,
        }
        if provider:
            base_meta["provider"] = provider
        if model:
            base_meta["model"] = model
        if query:
            base_meta["query"] = query
        if response:
            base_meta["response"] = response

        for step in steps:
            details = {
                **base_meta,
                **self._slim_details(step.step_metadata),
            }
            out.append(
                {
                    "execution_id": str(session.id),
                    "stage": step.stage_name,
                    "status": self._normalize_status(step.status),
                    "created_at": self._iso(step.created_at),
                    "route": route,
                    "mode": route,
                    "modality": self._infer_modality(route, step.stage_name, details),
                    "modality_route": self._infer_modality_route(route, step.stage_name, details),
                    "details": details,
                    "error_text": error_text or details.get("error"),
                }
            )

        if not steps:
            # Session without steps: emit a single synthetic row so it is still visible.
            details = dict(base_meta)
            out.append(
                {
                    "execution_id": str(session.id),
                    "stage": "session_summary",
                    "status": self._normalize_status(session.status),
                    "created_at": self._iso(session.created_at),
                    "route": route,
                    "mode": route,
                    "modality": self._infer_modality(route, "session_summary", details),
                    "modality_route": self._infer_modality_route(route, "session_summary", details),
                    "details": details,
                    "error_text": error_text,
                }
            )

        return out

    def _slim_details(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        if not raw:
            return {}
        out: dict[str, Any] = {}
        for key in _PRESERVED_DETAIL_KEYS:
            if key in raw:
                out[key] = raw[key]
        return out

    @staticmethod
    def _normalize_status(status: str | None) -> str:
        if not status:
            return "other"
        s = status.strip().lower()
        if s in ("ok", "success"):
            return "success"
        if s in ("error", "failed"):
            return "error"
        if s == "skipped":
            return "skipped"
        if s == "running":
            return "started"
        return "other"

    @staticmethod
    def _infer_modality(route: str, stage: str, details: dict[str, Any]) -> str | None:
        r = (route or "").lower()
        st = (stage or "").lower()
        if r in ("rag",) or st == "rag_search":
            return "rag"
        if r in ("text",):
            return "text"
        if r in ("image", "image_generation"):
            return "image"
        if r in ("audio", "voice"):
            return "audio"
        if r in ("document",):
            return "document"
        if r in ("log",):
            return "log"
        return None

    @staticmethod
    def _infer_modality_route(route: str, stage: str, details: dict[str, Any]) -> str:
        r = (route or "").lower()
        st = (stage or "").lower()
        if r in ("rag",) or st == "rag_search" or details.get("rag_used"):
            return "rag"
        if r in ("text",):
            return "text"
        if r in ("image", "image_generation"):
            return "image"
        if r in ("audio", "voice"):
            return "audio"
        if r in ("document",):
            return "document"
        return "other"

    @staticmethod
    def _iso(dt: datetime | None) -> str | None:
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
