"""
Dashboard workspace for admin console.

Returns aggregated system health and content metrics.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.dashboard_service import DashboardService

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return dashboard metrics."""
    service = DashboardService(db)
    return service.get_dashboard()
