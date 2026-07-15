"""
Content / Knowledge Base workspace for admin console.
Skeleton only — CRUD and sync logic will be implemented in later stages.
"""

from fastapi import APIRouter, Depends
from app.api.admin.dependencies import require_admin

router = APIRouter()


@router.get("/knowledge-base/status")
async def get_kb_status(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "status": "ok", "chromadb": {"chunks": 0}}


@router.get("/knowledge-base/sources")
async def list_sources(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "items": []}


@router.post("/knowledge-base/sources")
async def create_source(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "message": "Not implemented"}


@router.get("/knowledge-base/sources/{source_id}")
async def get_source(source_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "source_id": source_id, "message": "Not implemented"}


@router.patch("/knowledge-base/sources/{source_id}")
async def update_source(source_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "source_id": source_id, "message": "Not implemented"}


@router.delete("/knowledge-base/sources/{source_id}")
async def delete_source(source_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "source_id": source_id, "message": "Not implemented"}


@router.post("/knowledge-base/sync")
async def sync_knowledge_base(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "message": "Not implemented"}


@router.get("/knowledge-base/project-cards")
async def list_project_cards(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "items": []}


@router.post("/knowledge-base/project-cards")
async def create_project_card(admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "message": "Not implemented"}


@router.get("/knowledge-base/project-cards/{card_id}")
async def get_project_card(card_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "card_id": card_id, "message": "Not implemented"}


@router.patch("/knowledge-base/project-cards/{card_id}")
async def update_project_card(card_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "card_id": card_id, "message": "Not implemented"}


@router.delete("/knowledge-base/project-cards/{card_id}")
async def delete_project_card(card_id: str, admin: None = Depends(require_admin)):
    return {"workspace": "knowledge_base", "card_id": card_id, "message": "Not implemented"}
