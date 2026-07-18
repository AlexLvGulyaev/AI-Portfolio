"""
AI Provider Settings Service for AI Portfolio.

Source: Review Flow (services/ai_provider_settings.py)
Adapted for AI Portfolio:
- DB is the single source of truth for runtime provider parameters
  (model_name, temperature, max_tokens, base_url, is_enabled, is_active, is_fallback).
- API keys remain in environment variables only.
"""

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AIProviderSetting
from app.schemas.provider import AIProviderEffectiveOut, EffectiveProviderInfo
from app.services.providers.base import EffectiveProviderConfig, ProviderNotReadyError
from app.services.providers.factory import AIProviderFactory, get_implementation_status
from app.services.providers.gigachat_auth import (
    gigachat_credentials_configured,
    missing_gigachat_env_keys,
)

DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "gigachat": "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
}


class AIProviderSettingsService:
    """
    Service for managing AI provider settings.

    The database is the source of truth for runtime parameters.
    API keys are read from environment variables and never stored in the DB.
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

        if not active.is_enabled:
            warnings.append(
                f"Active provider '{active.provider_key}' is disabled; "
                "enable it or switch to another provider"
            )

        impl_status = get_implementation_status(active.provider_key)
        if impl_status == "not_implemented":
            warnings.append(f"Active provider '{active.provider_key}' is not implemented")

        return active, warnings

    def build_effective_config(self, row: AIProviderSetting) -> EffectiveProviderConfig:
        """
        Build EffectiveProviderConfig for a provider row from DB + env fallback.

        Args:
            row: AIProviderSetting row

        Returns:
            EffectiveProviderConfig ready for AIProviderFactory
        """
        provider_key = row.provider_key

        # API keys are always read from environment variables.
        api_key: str | None = None
        missing_env_keys: list[str] = []
        if provider_key == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                missing_env_keys.append(row.api_key_env_key or "OPENAI_API_KEY")
        elif provider_key == "gigachat":
            if gigachat_credentials_configured():
                api_key = os.environ.get("GIGACHAT_AUTH_KEY") or "configured"
            else:
                missing_env_keys.extend(missing_gigachat_env_keys())

        # Base URL priority: DB value -> env value -> hardcoded default.
        base_url = row.base_url
        if not base_url:
            if provider_key == "openai":
                base_url = os.environ.get("OPENAI_BASE_URL")
            elif provider_key == "gigachat":
                base_url = os.environ.get("GIGACHAT_BASE_URL")
        if not base_url and provider_key in DEFAULT_BASE_URLS:
            base_url = DEFAULT_BASE_URLS[provider_key]

        # Model name priority: DB value -> env value -> default.
        model_name = row.model_name
        if not model_name:
            if provider_key == "openai":
                model_name = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
            elif provider_key == "gigachat":
                model_name = os.environ.get("GIGACHAT_MODEL", "GigaChat-Max")

        # Runtime parameters from DB (seeded by migration 005). Defaults as safety net.
        temperature = row.temperature if row.temperature is not None else 0.7
        max_tokens = row.max_tokens if row.max_tokens is not None else 500

        readiness = "ready" if api_key or provider_key == "mock" else "missing_env_keys"

        return EffectiveProviderConfig(
            provider_key=provider_key,
            model_name=model_name,
            readiness=readiness,
            missing_env_keys=missing_env_keys,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def is_row_ready(self, row: AIProviderSetting) -> tuple[bool, list[str]]:
        """Check if provider row is ready to use."""
        impl = get_implementation_status(row.provider_key)
        if impl == "not_implemented":
            return False, []
        if row.provider_key == "mock":
            return True, []

        config = self.build_effective_config(row)
        return config.readiness == "ready", config.missing_env_keys

    def activate(self, provider_key: str) -> dict[str, Any]:
        """
        Activate provider.

        Args:
            provider_key: Provider identifier

        Returns:
            Updated provider setting

        Raises:
            HTTPException: If provider not found, not implemented or disabled
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

        # Activate selected provider and make sure it is not fallback.
        # Active provider cannot be fallback at the same time.
        for other in self.db.scalars(select(AIProviderSetting)).all():
            if other.provider_key == provider_key:
                other.is_active = True
                other.is_fallback = False
            else:
                other.is_active = False
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
            HTTPException: If provider not found, not implemented or disabled
        """
        row = self.get_by_key(provider_key)
        if get_implementation_status(provider_key) == "not_implemented":
            raise HTTPException(400, f"Provider '{provider_key}' is not implemented")

        if not row.is_enabled:
            raise HTTPException(
                400,
                f"Provider '{provider_key}' is disabled. Enable it before setting as fallback.",
            )

        # Set selected provider as fallback and make sure it is not active.
        # Fallback provider cannot be active at the same time.
        for other in self.db.scalars(select(AIProviderSetting)).all():
            if other.provider_key == provider_key:
                other.is_fallback = True
                other.is_active = False
            else:
                other.is_fallback = False
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
        allowed_fields = {
            "display_name",
            "model_name",
            "is_enabled",
            "temperature",
            "max_tokens",
            "base_url",
        }
        for key, val in data.items():
            if key not in allowed_fields:
                continue
            if val is not None:
                setattr(row, key, val)

        # If provider was disabled and is active/fallback, clear those flags.
        if data.get("is_enabled") is False:
            row.is_active = False
            row.is_fallback = False

        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(row)
        return self._to_dict(row)

    def test_provider(self, provider_key: str) -> dict[str, Any]:
        """
        Test provider connection using current DB settings + env API key.

        Args:
            provider_key: Provider identifier

        Returns:
            Dict with ok, readiness, message, missing_env_keys
        """
        row = self.get_by_key(provider_key)
        config = self.build_effective_config(row)
        impl = get_implementation_status(provider_key)

        if impl == "not_implemented":
            return {
                "provider_key": provider_key,
                "ok": False,
                "readiness": "not_implemented",
                "message": "Provider configured but not implemented",
                "missing_env_keys": config.missing_env_keys,
                "implementation_status": impl,
            }

        if config.missing_env_keys:
            return {
                "provider_key": provider_key,
                "ok": False,
                "readiness": "missing_env_keys",
                "message": f"Missing environment variables: {', '.join(config.missing_env_keys)}",
                "missing_env_keys": config.missing_env_keys,
                "implementation_status": impl,
            }

        try:
            provider = AIProviderFactory.create(provider_key, config=config)
            ok, message = provider.test_connection()
            return {
                "provider_key": provider_key,
                "ok": ok,
                "readiness": "ready" if ok else "error",
                "message": message,
                "missing_env_keys": [],
                "implementation_status": impl,
            }
        except ProviderNotReadyError as exc:
            return {
                "provider_key": provider_key,
                "ok": False,
                "readiness": "not_ready",
                "message": str(exc),
                "missing_env_keys": config.missing_env_keys,
                "implementation_status": impl,
            }
        except Exception as exc:
            return {
                "provider_key": provider_key,
                "ok": False,
                "readiness": "error",
                "message": str(exc),
                "missing_env_keys": [],
                "implementation_status": impl,
            }

    def _to_dict(self, row: AIProviderSetting) -> dict[str, Any]:
        """Convert provider setting to dictionary."""
        ready, missing = self.is_row_ready(row)
        impl = get_implementation_status(row.provider_key)

        effective_base_url = row.base_url
        if not effective_base_url and row.provider_key in DEFAULT_BASE_URLS:
            effective_base_url = DEFAULT_BASE_URLS[row.provider_key]

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
            "base_url": row.base_url,
            "api_key_env_key": row.api_key_env_key,
            "base_url_env_key": row.base_url_env_key,
            "effective_base_url": effective_base_url,
            "readiness": "ready" if ready else ("missing_env" if missing else "not_ready"),
            "missing_env_keys": missing,
            "implementation_status": impl,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
