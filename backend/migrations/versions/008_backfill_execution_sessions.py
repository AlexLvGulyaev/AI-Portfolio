"""Backfill execution sessions from existing operational logs

Revision ID: 008
Revises: 007
Create Date: 2026-07-18

"""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

# Import models via the path configured by env.py
from app.models.entities import ChatSession, ExecutionSession, ExecutionStep, OperationalLog

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    session = Session(bind=conn)

    # Pre-load existing chat session IDs to validate foreign keys without N+1 queries.
    valid_session_ids = {
        row[0] for row in session.execute(sa.select(ChatSession.id)).all()
    }

    def _resolve_session_id(session_id) -> tuple:
        """Return session_id if it exists in chat_sessions, otherwise None and a note."""
        if session_id and session_id in valid_session_ids:
            return session_id, None
        return None, {"original_session_id": str(session_id) if session_id else None, "session_missing": True}

    chat_logs = session.execute(
        sa.select(OperationalLog).where(OperationalLog.event_type == "chat_request")
    ).scalars().all()

    for log in chat_logs:
        metadata = log.log_metadata or {}
        rag_used = bool(metadata.get("rag_used"))
        fallback_used = bool(metadata.get("fallback_used"))
        from_cache = bool(log.from_cache)
        duration_ms = log.response_time_ms or 0
        created_at = log.created_at or datetime.now(timezone.utc)
        started_at = created_at - timedelta(milliseconds=duration_ms) if duration_ms else created_at

        resolved_session_id, session_note = _resolve_session_id(log.session_id)
        exec_metadata = {
            "backfilled": True,
            "rag_used": rag_used,
            "fallback_used": fallback_used,
            "from_cache": from_cache,
        }
        if session_note:
            exec_metadata.update(session_note)

        execution = ExecutionSession(
            session_id=resolved_session_id,
            user_id=log.user_id,
            event_type="chat_request",
            route="rag" if rag_used else "text",
            status=log.status or "ok",
            started_at=started_at,
            finished_at=created_at,
            duration_ms=duration_ms,
            provider_key=log.provider_key,
            model_name=log.model_name,
            execution_metadata=exec_metadata,
            created_at=created_at,
        )
        session.add(execution)
        session.flush()  # obtain execution.id

        # Build steps for a chat request. Durations are approximated proportionally.
        base_step_duration = max(1, duration_ms // 10) if duration_ms else 0
        step_started = started_at

        def _make_step(stage_name: str, step_order: int, status: str = "ok", step_meta: dict | None = None, duration: int | None = None) -> ExecutionStep:
            nonlocal step_started
            dur = duration if duration is not None else base_step_duration
            finished = step_started + timedelta(milliseconds=dur)
            step = ExecutionStep(
                execution_session_id=execution.id,
                stage_name=stage_name,
                step_order=step_order,
                status=status,
                started_at=step_started,
                finished_at=finished,
                duration_ms=dur,
                step_metadata=step_meta or {},
                created_at=step_started,
            )
            step_started = finished
            return step

        # 1. session_resolve
        session.add(_make_step("session_resolve", 1, step_meta=session_note or {}))
        # 2. memory_load
        session.add(_make_step("memory_load", 2))
        # 3. cache_check
        session.add(_make_step("cache_check", 3, step_meta={"cache_hit": from_cache}))
        # 4. rag_search
        if rag_used:
            session.add(_make_step("rag_search", 4))
        else:
            session.add(_make_step("rag_search", 4, status="skipped", step_meta={"reason": "no_rag"}, duration=0))
        # 5. prompt_build (skipped when served from cache)
        if from_cache:
            session.add(_make_step("prompt_build", 5, status="skipped", step_meta={"reason": "cache_hit"}, duration=0))
        else:
            session.add(_make_step("prompt_build", 5))
        # 6. provider_select
        session.add(_make_step("provider_select", 6, step_meta={"fallback_at_select": fallback_used}))
        # 7. provider_switch
        if fallback_used:
            session.add(_make_step("provider_switch", 7))
        else:
            session.add(_make_step("provider_switch", 7, status="skipped", step_meta={"reason": "primary_used"}, duration=0))
        # 8. llm_call
        if from_cache:
            session.add(_make_step("llm_call", 8, status="skipped", step_meta={"reason": "cache_hit"}, duration=0))
        else:
            session.add(_make_step("llm_call", 8))
        # 9. memory_save
        session.add(_make_step("memory_save", 9))
        # 10. log_write
        session.add(_make_step("log_write", 10, step_meta={"log_id": str(log.id)}))
        # 11. response_return
        session.add(_make_step("response_return", 11))

        log.execution_id = execution.id

    # Provider switch logs.
    switch_logs = session.execute(
        sa.select(OperationalLog).where(OperationalLog.event_type == "provider_switch")
    ).scalars().all()

    for log in switch_logs:
        created_at = log.created_at or datetime.now(timezone.utc)
        resolved_session_id, session_note = _resolve_session_id(log.session_id)
        exec_metadata = {"backfilled": True, **(log.log_metadata or {})}
        if session_note:
            exec_metadata.update(session_note)

        execution = ExecutionSession(
            session_id=resolved_session_id,
            user_id=log.user_id,
            event_type="provider_switch",
            route="log",
            status=log.status or "ok",
            started_at=created_at,
            finished_at=created_at,
            duration_ms=0,
            provider_key=log.provider_key,
            model_name=log.model_name,
            execution_metadata=exec_metadata,
            created_at=created_at,
        )
        session.add(execution)
        session.flush()

        session.add(ExecutionStep(
            execution_session_id=execution.id,
            stage_name="provider_switch",
            step_order=0,
            status="ok",
            started_at=created_at,
            finished_at=created_at,
            duration_ms=0,
            step_metadata=log.log_metadata or {},
            created_at=created_at,
        ))
        log.execution_id = execution.id

    # RAG query logs.
    rag_logs = session.execute(
        sa.select(OperationalLog).where(OperationalLog.event_type == "rag_query")
    ).scalars().all()

    for log in rag_logs:
        created_at = log.created_at or datetime.now(timezone.utc)
        duration_ms = log.response_time_ms or 0
        started_at = created_at - timedelta(milliseconds=duration_ms) if duration_ms else created_at
        resolved_session_id, session_note = _resolve_session_id(log.session_id)
        exec_metadata = {"backfilled": True, **(log.log_metadata or {})}
        if session_note:
            exec_metadata.update(session_note)

        execution = ExecutionSession(
            session_id=resolved_session_id,
            user_id=log.user_id,
            event_type="rag_query",
            route="rag",
            status=log.status or "ok",
            started_at=started_at,
            finished_at=created_at,
            duration_ms=duration_ms,
            provider_key=log.provider_key,
            model_name=log.model_name,
            execution_metadata=exec_metadata,
            created_at=created_at,
        )
        session.add(execution)
        session.flush()

        session.add(ExecutionStep(
            execution_session_id=execution.id,
            stage_name="rag_search",
            step_order=0,
            status="ok",
            started_at=started_at,
            finished_at=created_at,
            duration_ms=duration_ms,
            step_metadata=log.log_metadata or {},
            created_at=created_at,
        ))
        log.execution_id = execution.id

    session.commit()


def downgrade() -> None:
    conn = op.get_bind()
    session = Session(bind=conn)

    # Unlink operational logs from backfilled execution sessions.
    session.execute(
        sa.update(OperationalLog)
        .where(
            OperationalLog.execution_id.isnot(None),
            OperationalLog.event_type.in_(["chat_request", "provider_switch", "rag_query"]),
        )
        .values(execution_id=None)
    )

    # Delete only backfilled execution sessions (cascade removes steps).
    # JSONB contains check for backfilled=true.
    session.execute(
        sa.delete(ExecutionSession).where(
            ExecutionSession.execution_metadata.contains({"backfilled": True})
        )
    )

    session.commit()
