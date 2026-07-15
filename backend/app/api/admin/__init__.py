"""
Admin API package for AI Portfolio administrative console.
"""

from fastapi import APIRouter

from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.knowledge_base import router as knowledge_base_router
from app.api.admin.logs import router as logs_router
from app.api.admin.conversations import router as conversations_router

admin_router = APIRouter(prefix="/admin")

admin_router.include_router(dashboard_router, tags=["admin:dashboard"])
admin_router.include_router(knowledge_base_router, tags=["admin:knowledge_base"])
admin_router.include_router(logs_router, tags=["admin:logs"])
admin_router.include_router(conversations_router, tags=["admin:conversations"])
