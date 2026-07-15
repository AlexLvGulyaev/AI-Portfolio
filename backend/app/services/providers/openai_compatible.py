import json
import time
from typing import Any

from openai import OpenAI

from app.services.providers.base import AIProvider, EffectiveProviderConfig, ProviderNotReadyError


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, config: EffectiveProviderConfig) -> None:
        if not config.api_key:
            raise ProviderNotReadyError(f"API key not configured for {config.provider_key}")
        base_url = config.base_url or "https://api.openai.com/v1"
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=base_url)

    @property
    def provider_key(self) -> str:
        return self._config.provider_key

    @property
    def model_name(self) -> str:
        return self._config.model_name

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> str:
        """Generate text completion."""
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def generate_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate JSON completion."""
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def is_ready(self) -> bool:
        """Check if provider is ready to use."""
        return bool(self._config.api_key)

    def complete_json(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], int]:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        content = response.choices[0].message.content or "{}"
        latency_ms = int((time.perf_counter() - start) * 1000)
        return json.loads(content), latency_ms

    def complete_text(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=max(self._config.temperature, 0.3),
            max_tokens=self._config.max_tokens,
        )
        content = response.choices[0].message.content or ""
        latency_ms = int((time.perf_counter() - start) * 1000)
        return content.strip(), latency_ms

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._client.models.list()
            return True, "Connection OK"
        except Exception as exc:
            return False, str(exc)
