"""Pydantic schemas for AI Provider Settings."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AIProviderSettingBase(BaseModel):
    """Base schema for AI Provider Settings."""

    provider_key: str
    display_name: str | None = None
    model_name: str | None = None
    is_enabled: bool = True
    is_active: bool = False
    is_fallback: bool = False
    temperature: float = 0.7
    max_tokens: int = 500
    base_url: str | None = None


class AIProviderSettingOut(AIProviderSettingBase):
    """Output schema for AI Provider Settings."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIProviderSettingPatch(BaseModel):
    """Patch schema for AI Provider Settings."""

    display_name: str | None = None
    model_name: str | None = None
    is_enabled: bool | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    max_tokens: int | None = Field(None, ge=1, le=128000)
    base_url: str | None = None


class AIProviderEffectiveOut(BaseModel):
    """Effective provider configuration."""

    active: "EffectiveProviderInfo | None" = None
    fallback: "EffectiveProviderInfo | None" = None
    effective_model: str | None = None
    readiness: str
    missing_env_keys: list[str] = []
    warnings: list[str] = []


class EffectiveProviderInfo(BaseModel):
    """Provider information."""

    provider_key: str
    display_name: str | None
    model_name: str | None
    readiness: str
    missing_env_keys: list[str] = []
    base_url: str | None = None