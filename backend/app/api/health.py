"""
Health check endpoint for AI Portfolio Backend.

Based on Review Flow (health endpoint pattern).
"""

from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Basic health status
    """
    settings = get_settings()

    return {
        "status": "ok",
        "environment": settings.environment,
        "service": "ai-portfolio-backend"
    }