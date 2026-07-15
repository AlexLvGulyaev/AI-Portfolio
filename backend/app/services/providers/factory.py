"""
AI Provider factory for AI Portfolio.

Source: Review Flow (services/ai_providers/factory.py)
Used directly without modifications.
"""

import os
from typing import Type
from app.services.providers.base import AIProvider, EffectiveProviderConfig
from app.services.providers.openai_compatible import OpenAICompatibleProvider
from app.services.providers.gigachat_provider import GigaChatProvider
from app.services.providers.mock_provider import MockProvider


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
    def create(provider_key: str, model_name: str | None = None) -> AIProvider:
        """
        Create AI provider instance by key.

        Args:
            provider_key: Provider identifier (e.g., 'openai', 'gigachat')
            model_name: Model name (optional, uses default if not specified)

        Returns:
            AI provider instance

        Raises:
            ValueError: If provider is not implemented
        """
        # Get API key and other config from environment
        api_key = None
        base_url = None
        temperature = 0.7
        max_tokens = 500

        if provider_key == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")
            model = model_name or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
            # Try to get max_tokens from env
            env_max = os.environ.get("OPENAI_MAX_TOKENS", "").strip()
            if env_max.isdigit():
                max_tokens = int(env_max)
        elif provider_key == "gigachat":
            # GigaChat uses GIGACHAT_AUTH_KEY for authentication
            api_key = os.environ.get("GIGACHAT_AUTH_KEY")
            model = model_name or os.environ.get("GIGACHAT_MODEL", "GigaChat-Max")
            # Try to get max_tokens from env
            env_max = os.environ.get("GIGACHAT_MAX_TOKENS", "").strip()
            if env_max.isdigit():
                max_tokens = int(env_max)
        elif provider_key == "mock":
            # Mock provider doesn't need config
            config = EffectiveProviderConfig(
                provider_key="mock",
                model_name=model_name or "mock-model",
                readiness="ready",
                missing_env_keys=[],
            )
            return MockProvider(config)
        else:
            raise ValueError(f"Provider '{provider_key}' is not implemented")

        # Create config
        config = EffectiveProviderConfig(
            provider_key=provider_key,
            model_name=model,
            readiness="ready" if api_key else "missing_env_keys",
            missing_env_keys=[] if api_key else [f"{provider_key.upper()}_API_KEY"],
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Create provider instance
        provider_classes: dict[str, Type[AIProvider]] = {
            "openai": OpenAICompatibleProvider,
            "gigachat": GigaChatProvider,
        }

        if provider_key not in provider_classes:
            raise ValueError(f"Provider '{provider_key}' is not implemented")

        return provider_classes[provider_key](config)