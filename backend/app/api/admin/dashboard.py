"""
Dashboard workspace for admin console.
Skeleton only — full metrics will be implemented in later stages.
"""

from fastapi import APIRouter, Depends
from app.api.admin.dependencies import require_admin

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(admin: None = Depends(require_admin)):
    """Return dashboard skeleton."""
    return {
        "workspace": "dashboard",
        "status": "ok",
        "metrics": {
            "ai_providers": {"count": 0, "active": 0},
            "knowledge_base": {"sources": 0, "last_sync_at": None},
            "logs": {"total": 0},
            "conversations": {"total": 0, "active": 0},
        },
    }
