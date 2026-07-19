"""
Logs workspace for admin console.

Lists operational logs with filtering and pagination.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.logs_conversations_service import LogsConversationsService

router = APIRouter()


@router.get("/logs")
async def list_logs(
    event_type: str | None = Query(None, description="Filter by event type"),
    status: str | None = Query(None, description="Filter by status"),
    date_from: date | None = Query(None, description="Filter from date (UTC)"),
    date_to: date | None = Query(None, description="Filter to date (UTC)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return operational logs with optional filters and pagination."""
    service = LogsConversationsService(db)
    return service.list_logs(
        event_type=event_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
