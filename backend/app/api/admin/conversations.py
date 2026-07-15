"""
Conversations workspace for admin console.
Skeleton only — filtering and detail views will be implemented in later stages.
"""

from fastapi import APIRouter, Depends
from app.api.admin.dependencies import require_admin

router = APIRouter()


@router.get("/conversations")
async def list_conversations(admin: None = Depends(require_admin)):
    return {"workspace": "conversations", "items": []}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "conversations", "conversation_id": conversation_id, "messages": []}
