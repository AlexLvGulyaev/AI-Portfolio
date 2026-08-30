"""
Admin console audit helper (canon ai-curator).

Every successful admin-console mutation is written to operational_logs with
event_type="admin_action": action + resource_type + admin ip/user_agent +
details (changed field names only — never full bodies or secrets).

The Audit console reads the same operational_logs API; admin_action rows
show as their own type there.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.services.operational_log_service import OperationalLogService


def _client_ip(request: Request) -> str:
    """Client IP respecting nginx reverse-proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def log_admin_action(
    request: Request,
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    changed_fields: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an admin_console mutation to the audit log.

    Fire-and-forget by canon: an audit failure must never break the admin
    action itself, so any logging exception is swallowed.
    """
    metadata: dict[str, Any] = {
        "action": action,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id else None,
        "changed_fields": changed_fields or [],
        "ip": _client_ip(request),
        "user_agent": request.headers.get("user-agent"),
        "path": request.url.path,

    }
    if details:
        metadata["details"] = details
    try:
        OperationalLogService(db).log_event(
            event_type="admin_action",
            source="admin_console",
            query=f"{action} {resource_type}",
            response="ok",
            status="ok",
            metadata=metadata,
        )
    except Exception:
        # Audit must never break the admin action (canon: ai-curator).
        return