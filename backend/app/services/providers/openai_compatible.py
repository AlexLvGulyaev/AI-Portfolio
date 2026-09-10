import json
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import OpenAI

from app.services.providers.base import AIProvider, EffectiveProviderConfig, ProviderNotReadyError


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, config: EffectiveProviderConfig) -> None:
        if not config.api_key:
            raise ProviderNotReadyError(
                config.provider_key,
                [f"{config.provider_key.upper()}_API_KEY"],
            )
        base_url = config.base_url or "https://api.openai.com/v1"
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=base_url)
        self._async_client: Any = None  # AsyncOpenAI, лениво — только для стрима

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
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate text completion."""
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature if temperature is not None else self._config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self._config.max_tokens,
        )
        return response.choices[0].message.content or ""

    async def generate_json(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate JSON completion."""
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temperature if temperature is not None else self._config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self._config.max_tokens,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def generate_stream(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Потоковая генерация: stream=True (SOT: OpenAI SDK 1.59.5,
        chat.completions.create(stream=True), чанки delta.content)."""
        client = self._client
        if self._async_client is None:
            from openai import AsyncOpenAI

            self._async_client = AsyncOpenAI(
                api_key=self._config.api_key, base_url=self._client.base_url
            )
        client = self._async_client
        stream = await client.chat.completions.create(
            model=self._config.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature if temperature is not None else self._config.temperature,
            max_tokens=max_tokens if max_tokens is not None else self._config.max_tokens,
            stream=True,
        )
        try:
            async for chunk in stream:
                choices = chunk.choices or []
                if not choices:
                    continue
                delta = choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        finally:
            await stream.close()

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
