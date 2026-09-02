"""
Presale funnel analytics endpoints (§4.5).

Read-only: funnel over operational_logs + execution_sessions.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.presale_service import PresaleService

router = APIRouter()


@router.get("/presale/funnel")
async def get_presale_funnel(
    days: int = Query(30, description="Period in days (7/30/90, 0 = all time)"),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return presale funnel aggregates for the selected period."""
    service = PresaleService(db)
    try:
        return service.get_funnel(days=days)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/presale/visitors")
async def get_presale_visitors(
    step: str = Query(..., description="Funnel step key (visit/case_view/chat/inquiry)"),
    days: int = Query(30, description="Period in days (7/30/90, 0 = all time)"),
    lost: bool = Query(False, description="Lost on this step instead of reached"),
    card_slug: str | None = Query(None, description="Drill-down from top-cases breakdown"),
    channel: str | None = Query(None, description="Drill-down from inquiry channels breakdown"),
    sort: str = Query(
        "value",
        description="Visitor list order: value (default) / touches / recent",
    ),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Level 2: visitor clusters for one funnel step."""
    service = PresaleService(db)
    try:
        return service.get_step_visitors(
            step_key=step,
            days=days,
            lost=lost,
            card_slug=card_slug or None,
            channel=channel or None,
            sort=sort,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/presale/visitors/{visitor_id}")
async def get_presale_visitor_journey(
    visitor_id: str,
    days: int = Query(0, description="Period in days (7/30/90, 0 = all time)"),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Level 3: chronological touch list for a single visitor."""
    service = PresaleService(db)
    try:
        return service.get_visitor_journey(visitor_id=visitor_id, days=days)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc