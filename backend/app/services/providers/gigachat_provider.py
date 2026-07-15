import json
import os
import re
import time
from typing import Any

import httpx

from app.services.providers.base import AIProvider, EffectiveProviderConfig, ProviderNotReadyError
from app.services.providers.gigachat_auth import (
    fetch_access_token,
    gigachat_credentials_configured,
)

CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
DEFAULT_MODEL = "GigaChat-Max"
REQUEST_TIMEOUT = 60.0


class GigaChatProvider(AIProvider):
    def __init__(self, config: EffectiveProviderConfig) -> None:
        if not gigachat_credentials_configured():
            raise ProviderNotReadyError(
                "GigaChat credentials missing: set GIGACHAT_AUTH_KEY or "
                "GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET"
            )
        self._config = config
        self._scope_model = config.model_name or os.getenv("GIGACHAT_MODEL", DEFAULT_MODEL)
        env_max = os.getenv("GIGACHAT_MAX_TOKENS", "").strip()
        self._max_tokens = config.max_tokens or (int(env_max) if env_max.isdigit() else 500)

    @property
    def provider_key(self) -> str:
        return "gigachat"

    @property
    def model_name(self) -> str:
        return self._scope_model

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> str:
        """Generate text completion."""
        return self._chat(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
        )

    async def generate_json(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 500,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate JSON completion."""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=min(temperature, 0.2),
        )
        return self._parse_json_content(content)

    def is_ready(self) -> bool:
        """Check if provider is ready to use."""
        return gigachat_credentials_configured()

    def complete_json(self, system_prompt: str, user_prompt: str) -> tuple[dict[str, Any], int]:
        start = time.perf_counter()
        content = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=min(self._config.temperature, 0.2),
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return self._parse_json_content(content), latency_ms

    def complete_text(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        start = time.perf_counter()
        content = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=max(self._config.temperature, 0.3),
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return content.strip(), latency_ms

    def test_connection(self) -> tuple[bool, str]:
        try:
            fetch_access_token(timeout=20.0)
            return True, "GigaChat OAuth token obtained"
        except Exception as exc:
            return False, f"GigaChat auth failed: {exc}"

    def _chat(self, messages: list[dict[str, str]], *, temperature: float) -> str:
        token = fetch_access_token(timeout=REQUEST_TIMEOUT)
        payload = {
            "model": self._scope_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self._max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT) as client:
            response = client.post(CHAT_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            raise ValueError(f"GigaChat chat failed with status {response.status_code}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("GigaChat returned empty choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise ValueError("GigaChat returned empty content")
        return str(content)

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        text = content.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise ValueError("GigaChat returned invalid JSON for classification")
