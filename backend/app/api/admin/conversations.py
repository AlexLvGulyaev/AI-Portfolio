"""
Conversations workspace for admin console.

Lists chat sessions with pagination and returns session details with messages.
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
    is_active: bool | None = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return chat sessions with optional filters and pagination."""
    service = LogsConversationsService(db)
    return service.list_conversations(
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return a single chat session with its messages."""
    service = LogsConversationsService(db)
    return service.get_conversation(conversation_id)
