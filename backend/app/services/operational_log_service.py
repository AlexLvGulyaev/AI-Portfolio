"""
Operational Log Service for AI Portfolio.

Source: Review Flow (services/operational_log.py), PEcf09 (db_logger.py), Assistant Flow
Unified logging service combining requirements from all sources.

Required fields:
- PEcf09: user_id, source, query, response, from_cache, response_time_ms
- Assistant Flow: session_id, metadata
- Review Flow: event_type, model_name, latency_ms, status
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import OperationalLog


class OperationalLogService:
    """
    Unified operational logging service.

    Combines requirements from:
    - PEcf09: user_id, source, query, response, from_cache, response_time_ms
    - Assistant Flow: session_id, metadata
    - Review Flow: event_type, model_name, latency_ms, status, error_message
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def log_event(
        self,
        *,
        event_type: str,
        session_id: str | uuid.UUID | None = None,
        user_id: str | uuid.UUID | None = None,
        source: str | None = None,
        query: str | None = None,
        response: str | None = None,
        model_name: str | None = None,
        provider_key: str | None = None,
        from_cache: bool | None = None,
        response_time_ms: int | None = None,
        latency_ms: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """
        Log operational event.

        Args:
            event_type: Event type (e.g., 'chat_request', 'rag_query')
            session_id: Session ID (from Assistant Flow)
            user_id: User/visitor ID (from PEcf09)
            source: Source of request ('web', 'api') (from PEcf09)
            query: User query (from PEcf09)
            response: AI response (from PEcf09)
            model_name: Model name (from Review Flow)
            provider_key: Provider key (for AI Portfolio)
            from_cache: Was response from cache (from PEcf09)
            response_time_ms: Response time in ms (from PEcf09)
            latency_ms: Latency in ms (from Review Flow, same as response_time_ms)
            status: Status ('ok', 'error') (from Review Flow)
            error_message: Error message if any (from Review Flow)
            metadata: Additional metadata (from Assistant Flow)

        Returns:
            Log entry ID
        """
        # Support both latency_ms and response_time_ms (same field)
        final_latency = latency_ms or response_time_ms

        log_entry = OperationalLog(
            event_type=event_type,
            session_id=uuid.UUID(str(session_id)) if session_id else None,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            source=source,
            query=query,
            response=response,
            model_name=model_name,
            provider_key=provider_key,
            from_cache=from_cache,
            response_time_ms=final_latency,
            status=status,
            error_message=error_message,
            log_metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )

        self._db.add(log_entry)
        self._db.commit()
        self._db.refresh(log_entry)

        return log_entry.id

    def log_chat_request(
        self,
        *,
        session_id: str | uuid.UUID,
        user_id: str | uuid.UUID | None,
        query: str,
        response: str,
        model_name: str,
        provider_key: str,
        from_cache: bool = False,
        response_time_ms: int,
        status: str = "ok",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """
        Convenience method for logging chat requests.

        Combines PEcf09 and Review Flow logging for chat interactions.
        """
        return self.log_event(
            event_type="chat_request",
            session_id=session_id,
            user_id=user_id,
            source="web",
            query=query,
            response=response,
            model_name=model_name,
            provider_key=provider_key,
            from_cache=from_cache,
            response_time_ms=response_time_ms,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )

    def log_rag_query(
        self,
        *,
        session_id: str | uuid.UUID | None = None,
        user_id: str | uuid.UUID | None = None,
        query: str,
        response: str,
        model_name: str | None = None,
        from_cache: bool = False,
        response_time_ms: int,
        status: str = "ok",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """
        Convenience method for logging RAG queries.
        """
        return self.log_event(
            event_type="rag_query",
            session_id=session_id,
            user_id=user_id,
            source="rag",
            query=query,
            response=response,
            model_name=model_name,
            from_cache=from_cache,
            response_time_ms=response_time_ms,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )

    def log_provider_switch(
        self,
        *,
        provider_key: str,
        model_name: str | None = None,
        status: str = "ok",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """
        Convenience method for logging provider switches.
        """
        return self.log_event(
            event_type="provider_switch",
            provider_key=provider_key,
            model_name=model_name,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )