"""
AI Provider factory for AI Portfolio.

Source: Review Flow (services/ai_providers/factory.py)
Adapted for AI Portfolio:
- create() accepts an optional EffectiveProviderConfig built from the DB.
- If config is not provided, factory falls back to environment variables for
  backward compatibility / tests.
"""

import os
from typing import Type

from app.services.providers.base import AIProvider, EffectiveProviderConfig
from app.services.providers.gigachat_provider import GigaChatProvider
from app.services.providers.mock_provider import MockProvider
from app.services.providers.openai_compatible import OpenAICompatibleProvider


DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
}


def get_implementation_status(provider_key: str) -> str:
    """
    Check implementation status for a provider.

    Returns:
        "implemented" if provider is available
        "not_implemented" if provider is not available
    """
    provider_classes: dict[str, Type[AIProvider]] = {
        "openai": OpenAICompatibleProvider,
        "gigachat": GigaChatProvider,
        "mock": MockProvider,
    }

    return "implemented" if provider_key in provider_classes else "not_implemented"


class AIProviderFactory:
    """Factory for creating AI provider instances."""

    @staticmethod
    def create(
        provider_key: str,
        model_name: str | None = None,
        config: EffectiveProviderConfig | None = None,
    ) -> AIProvider:
        """
        Create AI provider instance by key.

        Args:
            provider_key: Provider identifier (e.g., 'openai', 'gigachat')
            model_name: Deprecated optional model name. Use config.model_name instead.
            config: EffectiveProviderConfig built from DB + env. If omitted,
                    factory builds a minimal config from environment variables.

        Returns:
            AI provider instance

        Raises:
            ValueError: If provider is not implemented
        """
        provider_classes: dict[str, Type[AIProvider]] = {
            "openai": OpenAICompatibleProvider,
            "gigachat": GigaChatProvider,
            "mock": MockProvider,
        }

        if provider_key not in provider_classes:
            raise ValueError(f"Provider '{provider_key}' is not implemented")

        if config is None:
            config = AIProviderFactory._config_from_env(provider_key, model_name)

        return provider_classes[provider_key](config)

    @staticmethod
    def _config_from_env(
        provider_key: str,
        model_name: str | None = None,
    ) -> EffectiveProviderConfig:
        """Build a minimal EffectiveProviderConfig from environment variables."""
        api_key = None
        base_url = None
        temperature = 0.7
        max_tokens = 500

        if provider_key == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URLS.get("openai")
            model = model_name or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
            env_max = os.environ.get("OPENAI_MAX_TOKENS", "").strip()
            if env_max.isdigit():
                max_tokens = int(env_max)
        elif provider_key == "gigachat":
            from app.services.providers.gigachat_auth import gigachat_credentials_configured

            if gigachat_credentials_configured():
                api_key = os.environ.get("GIGACHAT_AUTH_KEY") or "configured"
            model = model_name or os.environ.get("GIGACHAT_MODEL", "GigaChat-Max")
            base_url = (
                os.environ.get("GIGACHAT_BASE_URL")
                or "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
            )
            env_max = os.environ.get("GIGACHAT_MAX_TOKENS", "").strip()
            if env_max.isdigit():
                max_tokens = int(env_max)
        elif provider_key == "mock":
            return EffectiveProviderConfig(
                provider_key="mock",
                model_name=model_name or "mock-model",
                readiness="ready",
                missing_env_keys=[],
            )
        else:
            raise ValueError(f"Provider '{provider_key}' is not implemented")

        return EffectiveProviderConfig(
            provider_key=provider_key,
            model_name=model,
            readiness="ready" if api_key else "missing_env_keys",
            missing_env_keys=[] if api_key else [f"{provider_key.upper()}_API_KEY"],
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
        )
