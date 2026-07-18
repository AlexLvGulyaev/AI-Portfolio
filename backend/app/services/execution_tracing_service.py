"""
Execution tracing service for AI Portfolio.

Records step-level traces of chat requests through ChatOrchestrator.
Each execution session represents one pass of process_request and is linked
back to the summary operational_log entry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import ExecutionSession, ExecutionStep, OperationalLog


class ExecutionTracingService:
    """Records execution sessions and steps for operational observability."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def start_session(
        self,
        *,
        session_id: str | uuid.UUID | None = None,
        user_id: str | uuid.UUID | None = None,
        event_type: str = "chat_request",
        route: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Start a new execution session and return its ID."""
        execution = ExecutionSession(
            session_id=uuid.UUID(str(session_id)) if session_id else None,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            event_type=event_type,
            route=route,
            status="running",
            started_at=datetime.utcnow(),
            execution_metadata=metadata or {},
        )
        self._db.add(execution)
        self._db.commit()
        self._db.refresh(execution)
        return execution.id

    def finish_session(
        self,
        execution_id: str | uuid.UUID,
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionSession:
        """Finish an execution session, computing duration from started_at."""
        execution = self._db.get(ExecutionSession, uuid.UUID(str(execution_id)))
        if not execution:
            raise ValueError(f"ExecutionSession {execution_id} not found")

        finished_at = datetime.utcnow()
        started_at = execution.started_at or finished_at
        duration_ms = max(
            0,
            int((finished_at - started_at).total_seconds() * 1000),
        )

        execution.status = status
        execution.finished_at = finished_at
        execution.duration_ms = duration_ms
        if metadata:
            execution.execution_metadata = {
                **(execution.execution_metadata or {}),
                **metadata,
            }

        self._db.commit()
        self._db.refresh(execution)
        return execution

    def set_session_provider(
        self,
        execution_id: str | uuid.UUID,
        *,
        provider_key: str,
        model_name: str,
    ) -> ExecutionSession:
        """Record the provider/model actually used for the execution."""
        execution = self._db.get(ExecutionSession, uuid.UUID(str(execution_id)))
        if not execution:
            raise ValueError(f"ExecutionSession {execution_id} not found")

        execution.provider_key = provider_key
        execution.model_name = model_name
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def set_session_route(
        self,
        execution_id: str | uuid.UUID,
        route: str,
    ) -> ExecutionSession:
        """Update execution route once pipeline decisions are known (e.g. rag vs text)."""
        execution = self._db.get(ExecutionSession, uuid.UUID(str(execution_id)))
        if not execution:
            raise ValueError(f"ExecutionSession {execution_id} not found")

        execution.route = route
        self._db.commit()
        self._db.refresh(execution)
        return execution

    def start_step(
        self,
        execution_id: str | uuid.UUID,
        stage_name: str,
        step_order: int,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Start a new step within an execution session."""
        step = ExecutionStep(
            execution_session_id=uuid.UUID(str(execution_id)),
            stage_name=stage_name,
            step_order=step_order,
            status="running",
            started_at=datetime.utcnow(),
            step_metadata=metadata or {},
        )
        self._db.add(step)
        self._db.commit()
        self._db.refresh(step)
        return step.id

    def finish_step(
        self,
        step_id: str | uuid.UUID,
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionStep:
        """Finish a step, computing its duration."""
        step = self._db.get(ExecutionStep, uuid.UUID(str(step_id)))
        if not step:
            raise ValueError(f"ExecutionStep {step_id} not found")

        finished_at = datetime.utcnow()
        started_at = step.started_at or finished_at
        duration_ms = max(
            0,
            int((finished_at - started_at).total_seconds() * 1000),
        )

        step.status = status
        step.finished_at = finished_at
        step.duration_ms = duration_ms
        if metadata:
            step.step_metadata = {
                **(step.step_metadata or {}),
                **metadata,
            }

        self._db.commit()
        self._db.refresh(step)
        return step

    def skip_step(
        self,
        execution_id: str | uuid.UUID,
        stage_name: str,
        step_order: int,
        metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Record a skipped step with zero duration."""
        now = datetime.utcnow()
        step = ExecutionStep(
            execution_session_id=uuid.UUID(str(execution_id)),
            stage_name=stage_name,
            step_order=step_order,
            status="skipped",
            started_at=now,
            finished_at=now,
            duration_ms=0,
            step_metadata=metadata or {},
        )
        self._db.add(step)
        self._db.commit()
        self._db.refresh(step)
        return step.id

    def link_operational_log(
        self,
        execution_id: str | uuid.UUID,
        operational_log_id: str | uuid.UUID,
    ) -> None:
        """Link an operational log entry to its execution session."""
        log_entry = self._db.get(OperationalLog, uuid.UUID(str(operational_log_id)))
        if not log_entry:
            raise ValueError(f"OperationalLog {operational_log_id} not found")

        log_entry.execution_id = uuid.UUID(str(execution_id))
        self._db.commit()
