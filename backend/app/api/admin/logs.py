"""
Logs workspace for admin console.
Skeleton only — filtering and pagination will be implemented in later stages.
"""

from fastapi import APIRouter, Depends
from app.api.admin.dependencies import require_admin

router = APIRouter()


@router.get("/logs")
async def list_logs(admin: None = Depends(require_admin)):
    return {"workspace": "logs", "items": []}
