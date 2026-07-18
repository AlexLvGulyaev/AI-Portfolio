"""
Execution sessions admin endpoints.

Provides operational tracing data for the Logs workspace.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.execution_sessions_service import ExecutionSessionsAdminService

router = APIRouter()


@router.get("/execution-sessions")
async def list_execution_sessions(
    route: str | None = Query(None, description="Filter by route: all/text/rag/log"),
    status: str | None = Query(None, description="Filter by status: ok/error"),
    date_from: date | None = Query(None, description="Filter from date (UTC)"),
    date_to: date | None = Query(None, description="Filter to date (UTC)"),
    search: str | None = Query(None, description="Search provider/model/event type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return execution sessions with filters and pagination."""
    service = ExecutionSessionsAdminService(db)
    return service.list_sessions(
        route=route,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/execution-sessions/{execution_id}")
async def get_execution_session(
    execution_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return execution session details including steps and linked operational log."""
    service = ExecutionSessionsAdminService(db)
    return service.get_session(execution_id)
