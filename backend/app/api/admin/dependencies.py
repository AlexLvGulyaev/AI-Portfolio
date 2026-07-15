"""
Admin authentication dependency.

Simple single-token authentication via Authorization: Bearer <ADMIN_API_TOKEN>.
No JWT, users, roles, or RBAC in v1.
"""

from fastapi import Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings

security = HTTPBearer(auto_error=False)


def require_admin(authorization: str | None = Header(None)) -> None:
    """Verify Authorization: Bearer <ADMIN_API_TOKEN> header."""
    settings = get_settings()
    token = settings.admin_api_token

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing Authorization header",
        )

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Authorization scheme. Use Bearer token",
        )

    if credentials != token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )
