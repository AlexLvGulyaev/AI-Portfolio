"""
Admin AI provider settings API.

Database is the source of truth for runtime provider parameters.
API keys remain in environment variables and are never exposed through this API.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.schemas.provider import AIProviderSettingPatch
from app.services.ai_provider_settings_service import AIProviderSettingsService

router = APIRouter()


@router.get("/ai-providers")
async def list_ai_providers(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all configured AI providers with runtime parameters from DB."""
    return AIProviderSettingsService(db).list_settings()


@router.patch("/ai-providers/{provider_key}")
async def patch_ai_provider(
    provider_key: str,
    body: AIProviderSettingPatch,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update provider runtime parameters (model, temperature, max_tokens, base_url, enabled)."""
    service = AIProviderSettingsService(db)
    return service.patch_setting(provider_key, body.model_dump(exclude_unset=True))


@router.post("/ai-providers/{provider_key}/activate")
async def activate_ai_provider(
    provider_key: str,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Set provider as the active provider. Disabled providers cannot be activated."""
    return AIProviderSettingsService(db).activate(provider_key)


@router.post("/ai-providers/{provider_key}/set-fallback")
async def set_fallback_ai_provider(
    provider_key: str,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Set provider as the fallback provider. Disabled providers cannot be fallback."""
    return AIProviderSettingsService(db).set_fallback(provider_key)


@router.post("/ai-providers/{provider_key}/test")
async def test_ai_provider(
    provider_key: str,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Test provider connection using current DB settings + env API key."""
    return AIProviderSettingsService(db).test_provider(provider_key)
