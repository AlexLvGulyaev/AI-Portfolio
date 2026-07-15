"""
AI Provider Settings Service for AI Portfolio.

Source: Review Flow (services/ai_provider_settings.py)
Adapted for AI Portfolio (simplified, removed admin endpoints).
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AIProviderSetting
from app.services.providers.factory import get_implementation_status


class AIProviderSettingsService:
    """
    Service for managing AI provider settings.

    Source: Review Flow (AIProviderSettingsService)
    Adapted for AI Portfolio:
    - Removed admin endpoints (will be added in later stage)
    - Simplified for portfolio use case
    - Focuses on service layer only
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_settings(self) -> list[dict[str, Any]]:
        """
        List all provider settings.

        Returns:
            List of provider settings
        """
        rows = self.db.scalars(
            select(AIProviderSetting).order_by(AIProviderSetting.provider_key)
        ).all()
        return [self._to_dict(r) for r in rows]

    def get_by_key(self, provider_key: str) -> AIProviderSetting:
        """
        Get provider setting by key.

        Args:
            provider_key: Provider identifier

        Returns:
            Provider setting

        Raises:
            HTTPException: If provider not found
        """
        row = self.db.scalars(
            select(AIProviderSetting).where(AIProviderSetting.provider_key == provider_key)
        ).first()
        if not row:
            raise HTTPException(404, f"Provider '{provider_key}' not found")
        return row

    def get_active(self) -> AIProviderSetting | None:
        """
        Get active provider setting.

        Returns:
            Active provider setting or None
        """
        return self.db.scalars(
            select(AIProviderSetting).where(AIProviderSetting.is_active.is_(True))
        ).first()

    def get_fallback(self) -> AIProviderSetting | None:
        """
        Get fallback provider setting.

        Returns:
            Fallback provider setting or None
        """
        return self.db.scalars(
            select(AIProviderSetting).where(AIProviderSetting.is_fallback.is_(True))
        ).first()

    def get_active_with_fallback(self) -> tuple[AIProviderSetting | None, AIProviderSetting | None]:
        """
        Get both active and fallback providers.

        Returns:
            Tuple of (active_provider, fallback_provider)
        """
        return self.get_active(), self.get_fallback()

    def get_effective_provider(self) -> tuple[AIProviderSetting | None, list[str]]:
        """
        Get effective provider and any warnings.

        Returns:
            Tuple of (provider, warnings)
        """
        active = self.get_active()
        warnings: list[str] = []

        if not active:
            warnings.append("No active provider configured")
            return None, warnings

        impl_status = get_implementation_status(active.provider_key)
        if impl_status == "not_implemented":
            warnings.append(f"Active provider '{active.provider_key}' is not implemented")

        return active, warnings

    def activate(self, provider_key: str) -> dict[str, Any]:
        """
        Activate provider.

        Args:
            provider_key: Provider identifier

        Returns:
            Updated provider setting

        Raises:
            HTTPException: If provider not found or not enabled
        """
        row = self.get_by_key(provider_key)
        if not row.is_enabled:
            raise HTTPException(
                400,
                f"Provider '{provider_key}' is disabled. Enable it before activation.",
            )

        impl_status = get_implementation_status(provider_key)
        if impl_status == "not_implemented":
            raise HTTPException(400, f"Provider '{provider_key}' is not implemented")

        # Deactivate all other providers
        for other in self.db.scalars(select(AIProviderSetting)).all():
            other.is_active = other.provider_key == provider_key
            other.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def set_fallback(self, provider_key: str) -> dict[str, Any]:
        """
        Set provider as fallback.

        Args:
            provider_key: Provider identifier

        Returns:
            Updated provider setting

        Raises:
            HTTPException: If provider not found or not implemented
        """
        row = self.get_by_key(provider_key)
        if get_implementation_status(provider_key) == "not_implemented":
            raise HTTPException(400, f"Provider '{provider_key}' is not implemented")

        if not row.is_enabled:
            raise HTTPException(
                400,
                f"Provider '{provider_key}' is disabled. Enable it before setting as fallback.",
            )

        # Remove fallback from all other providers
        for other in self.db.scalars(select(AIProviderSetting)).all():
            other.is_fallback = other.provider_key == provider_key
            other.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def patch_setting(self, provider_key: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Patch provider setting.

        Args:
            provider_key: Provider identifier
            data: Fields to update

        Returns:
            Updated provider setting
        """
        row = self.get_by_key(provider_key)
        for key, val in data.items():
            if val is not None:
                setattr(row, key, val)
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def _to_dict(self, row: AIProviderSetting) -> dict[str, Any]:
        """Convert provider setting to dictionary."""
        return {
            "id": str(row.id),
            "provider_key": row.provider_key,
            "display_name": row.display_name,
            "model_name": row.model_name,
            "is_enabled": row.is_enabled,
            "is_active": row.is_active,
            "is_fallback": row.is_fallback,
            "temperature": row.temperature,
            "max_tokens": row.max_tokens,
            "api_key_env_key": row.api_key_env_key,
            "base_url_env_key": row.base_url_env_key,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }