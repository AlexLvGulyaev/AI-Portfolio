"""
Base provider interface for AI Portfolio.

Source: Review Flow (services/ai_providers/base.py)
Used directly without modifications.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class EffectiveProviderConfig:
    """Effective configuration for a provider."""

    provider_key: str
    model_name: str | None
    readiness: str  # "ready", "missing_env_keys", "not_implemented", "no_api_key"
    missing_env_keys: list[str]
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 500
    temperature: float = 0.7


class ProviderNotReadyError(Exception):
    """Raised when trying to use a provider that is not ready."""

    def __init__(self, provider_key: str, missing_keys: list[str]):
        self.provider_key = provider_key
        self.missing_keys = missing_keys
        super().__init__(
            f"Provider '{provider_key}' is not ready. Missing env keys: {missing_keys}"
        )


class AIProvider(ABC):
    """Base class for AI providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> str:
        """Generate text completion."""
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate JSON completion."""
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if provider is ready to use."""
        ...