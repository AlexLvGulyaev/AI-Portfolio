"""
Public visit tracking endpoint.

Records anonymous site visits in operational_logs with a stable visitor_id
stored in the browser's localStorage. No personal data is collected.
"""

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.database import get_db
from app.services.operational_log_service import OperationalLogService

router = APIRouter()


class TrackVisitRequest(BaseModel):
    visitor_id: str | None = Field(None, description="Stable anonymous visitor id")
    path: str | None = Field(None, description="Current page path")
    referrer: str | None = Field(None, description="Referrer URL")
    user_agent: str | None = Field(None, description="Browser user agent")


class TrackVisitResponse(BaseModel):
    visitor_id: str


def _get_client_ip(request: Request) -> str:
    """Return client IP considering nginx reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


@router.post("/track-visit", response_model=TrackVisitResponse)
async def track_visit(
    request: Request,
    payload: TrackVisitRequest,
    db: Session = Depends(get_db),
):
    """
    Record an anonymous visit to the public site.

    Creates operational_log with event_type='site_visit'. Returns visitor_id
    (new one generated if not provided).
    """
    visitor_id = payload.visitor_id or str(uuid.uuid4())
    logger = OperationalLogService(db)
    client_ip = _get_client_ip(request)
    user_agent = payload.user_agent or request.headers.get("user-agent")

    logger.log_event(
        event_type="site_visit",
        source="web",
        query=payload.path or request.headers.get("referer") or "/",
        response=payload.referrer or request.headers.get("referer"),
        status="ok",
        metadata={
            "visitor_id": visitor_id,
            "ip": client_ip,
            "user_agent": user_agent,
        },
    )

    return TrackVisitResponse(visitor_id=visitor_id)
