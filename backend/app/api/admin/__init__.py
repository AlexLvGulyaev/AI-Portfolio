"""
Admin API package for AI Portfolio administrative console.
"""

from fastapi import APIRouter

from app.api.admin.ai_providers import router as ai_providers_router
from app.api.admin.auth import router as auth_router
from app.api.admin.chat_preview import router as chat_preview_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.documents import router as documents_router
from app.api.admin.knowledge_base import router as knowledge_base_router
from app.api.admin.logs import router as logs_router
from app.api.admin.conversations import router as conversations_router
from app.api.admin.execution_sessions import router as execution_sessions_router
from app.api.admin.presale import router as presale_router
from app.api.admin.prompt import router as prompt_router
from app.api.admin.retrieval import router as retrieval_router

admin_router = APIRouter(prefix="/admin")

admin_router.include_router(auth_router, tags=["admin:auth"])
admin_router.include_router(dashboard_router, tags=["admin:dashboard"])
admin_router.include_router(knowledge_base_router, tags=["admin:knowledge_base"])
admin_router.include_router(documents_router, tags=["admin:documents"])
admin_router.include_router(chat_preview_router, tags=["admin:chat_preview"])
admin_router.include_router(logs_router, tags=["admin:logs"])
admin_router.include_router(conversations_router, tags=["admin:conversations"])
admin_router.include_router(ai_providers_router, tags=["admin:ai_providers"])
admin_router.include_router(execution_sessions_router, tags=["admin:execution_sessions"])
admin_router.include_router(retrieval_router, tags=["admin:retrieval"])
admin_router.include_router(prompt_router, tags=["admin:system_prompt"])
admin_router.include_router(presale_router, tags=["admin:presale"])
