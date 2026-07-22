"""
Mock Provider for AI Portfolio.

Simplified version for AI Portfolio (without ClassificationResult).
Used for testing without real AI provider.
"""

import time
from typing import Any

from app.services.providers.base import AIProvider, EffectiveProviderConfig


class MockProvider(AIProvider):
    """Mock provider for testing."""

    def __init__(self, config: EffectiveProviderConfig) -> None:
        self._config = config

    @property
    def provider_key(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._config.model_name or "mock-model"

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> str:
        """Generate mock text completion."""
        start = time.perf_counter()
        # Simulate processing time
        time.sleep(0.1)

        # Generate simple mock response
        if "кейс" in prompt.lower() or "case" in prompt.lower():
            return "AI Portfolio включает следующие кейсы: Assistant Flow, Review Flow, Lead Qualification, HR Assistant — LoRA Fine-Tuning, Prompt Review, Telegram AI Gateway, Competitor Monitor AI."
        elif "услуг" in prompt.lower() or "service" in prompt.lower():
            return "Я предоставляю услуги по AI-автоматизации: интеграция AI-ассистентов, разработка RAG-систем, автоматизация бизнес-процессов."
        else:
            return "Это mock-ответ для тестирования. Для получения реальных ответов настройте OpenAI или GigaChat провайдер."

    async def generate_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate mock JSON completion."""
        return {
            "answer": "Mock JSON response",
            "confidence": 0.9,
            "provider": "mock"
        }

    def is_ready(self) -> bool:
        """Mock provider is always ready."""
        return True