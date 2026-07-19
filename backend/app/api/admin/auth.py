"""
Admin authentication endpoint with audit logging.

Authentication remains stateless via ADMIN_API_TOKEN. This endpoint exists
solely to record the fact of a login attempt in operational_logs.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.operational_log_service import OperationalLogService

router = APIRouter()


class LoginRequest(BaseModel):
    token: str


class LoginResponse(BaseModel):
    success: bool


def _get_client_ip(request: Request) -> str:
    """Return client IP considering nginx reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
async def admin_login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Verify admin token and log the login attempt.

    On success: operational_log.event_type = 'admin_login', status = 'ok'.
    On failure: operational_log.event_type = 'admin_login', status = 'error'.
    """
    settings = get_settings()
    logger = OperationalLogService(db)
    client_ip = _get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    expected_token = settings.admin_api_token
    is_valid = bool(payload.token) and payload.token == expected_token

    log_status = "ok" if is_valid else "error"
    error_message = None if is_valid else "Invalid admin token"

    logger.log_event(
        event_type="admin_login",
        source="admin",
        query="admin_login",
        response="success" if is_valid else "failed",
        status=log_status,
        error_message=error_message,
        metadata={
            "ip": client_ip,
            "user_agent": user_agent,
            "via": "LoginPage",
        },
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )

    return LoginResponse(success=True)
