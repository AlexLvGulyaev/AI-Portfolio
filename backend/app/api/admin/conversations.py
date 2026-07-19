"""
Conversations workspace for admin console.

Lists chat sessions with filtering and returns session details with messages,
paired dialog turns, execution timeline and memory budget.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.logs_conversations_service import LogsConversationsService

router = APIRouter()


@router.get("/conversations")
async def list_conversations(
    hours: int | None = Query(None, ge=1, le=24 * 365, description="Window in hours filtered by updated_at"),
    route: str | None = Query(None, description="Filter by route of latest execution session"),
    active_only: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search by session_id, visitor_id or mode"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return chat sessions with optional filters and pagination."""
    service = LogsConversationsService(db)
    return service.list_conversations(
        hours=hours,
        route=route,
        active_only=active_only,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return a single chat session with messages, turns, executions and budget."""
    service = LogsConversationsService(db)
    return service.get_conversation(conversation_id)
