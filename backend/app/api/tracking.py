"""
Public visit tracking endpoint.

Records anonymous site visits in operational_logs with a stable visitor_id
stored in the browser's localStorage. No personal data is collected.
"""

from typing import Any, Literal

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


# Presale funnel event types (§4.5, решение о хранилище — ARCHITECTURE.md §8.4).
# chat_feedback — не шаг воронки, а оценка ответа ассистента (👍/👎, 03.09);
# консоль «Пресейл» фильтрует по явным типам и не задевается новым типом.
# Whitelist: произвольные типы не принимаются, чтобы не засорять воронку.
ALLOWED_PRESALE_EVENT_TYPES: tuple[str, ...] = ("case_view", "inquiry", "chat_feedback")

# Разрешённые ключи метаданных события (visitor_id проставляется сервером).
ALLOWED_PRESALE_METADATA_KEYS: tuple[str, ...] = (
    "card_slug",
    "card_title",
    "external_url",
    "channel",
    "label",
    "rating",
    "question_preview",
)


class TrackEventRequest(BaseModel):
    event_type: Literal["case_view", "inquiry", "chat_feedback"] = Field(
        description="Presale funnel event type (chat_feedback — оценка ответа ассистента)"
    )
    visitor_id: str | None = Field(None, description="Stable anonymous visitor id")
    path: str | None = Field(None, description="Current page path")
    metadata: dict[str, Any] | None = Field(
        None, description="Event context (card/channel info)"
    )


class TrackEventResponse(BaseModel):
    event_type: str
    visitor_id: str


def _filter_presale_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only whitelisted, scalar metadata keys."""
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key in ALLOWED_PRESALE_METADATA_KEYS
        and isinstance(value, (str, int, float, bool))
    }


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


@router.post("/track-event", response_model=TrackEventResponse)
async def track_event(
    request: Request,
    payload: TrackEventRequest,
    db: Session = Depends(get_db),
):
    """
    Record one presale funnel event (case_view / inquiry) in operational_logs.

    visitor_id is attached server-side (stable anonymous id from localStorage).
    Unknown event types and non-whitelisted metadata keys are rejected/filtered.
    """
    visitor_id = payload.visitor_id or str(uuid.uuid4())
    logger = OperationalLogService(db)
    client_ip = _get_client_ip(request)

    # ip проставляется сервером (как visitor_id): клиент не передаёт и
    # подделать не может. География посетителей — §4.5, решение 02.09.
    metadata: dict[str, Any] = {
        "visitor_id": visitor_id,
        "ip": client_ip,
        **_filter_presale_metadata(payload.metadata),
    }

    logger.log_event(
        event_type=payload.event_type,
        source="web",
        query=payload.path or "/",
        status="ok",
        metadata=metadata,
    )

    return TrackEventResponse(event_type=payload.event_type, visitor_id=visitor_id)
