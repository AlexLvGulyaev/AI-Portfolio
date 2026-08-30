"""
Unit-тесты admin chat-preview (канал проверки KB владельцем, §5.1 п. 9).

Примечание: TestClient не используется (в среде starlette-testclient несовместим
с установленным httpx) — эндпойнт вызывается напрямую как async-функция.

- require_admin без токена → 403 (fail-closed);
- ChatOrchestrator строится с include_hidden=True и visitor_id="admin-preview";
- внутреннее исключение оборачивается в понятный 500.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

import app.api.admin.chat_preview as cp
from app.api.admin.dependencies import require_admin

_CAPTURED: dict = {}


class FakeOrch:
    def __init__(self, **kwargs):
        _CAPTURED.update(kwargs)

    async def process_request(self, **kw):
        _CAPTURED["process_request"] = kw
        return SimpleNamespace(
            answer="Ответ владельца",
            session_id=uuid.uuid4(),
            sources=["r/p"],
            metadata={"sources_detail": [{"repo": "r", "path": "p"}]},
            provider="openai", model="m", cache_hit=False, rag_used=True,
            latency_ms=42, user_id=None,
        )


class BoomOrch:
    def __init__(self, **kwargs):
        pass

    async def process_request(self, **kw):
        raise RuntimeError("внутренняя ошибка сервиса")


def _fake_rag(config):
    svc = MagicMock()
    svc.config = SimpleNamespace(collection_name="c")
    return svc


def _fake_request() -> Any:
    req = MagicMock()
    req.headers = {}
    return req


def test_chat_preview_requires_token():
    """require_admin без Authorization: Bearer — 403 (fail-closed)."""
    with pytest.raises(HTTPException) as excinfo:
        cp.require_admin(None)
    assert excinfo.value.status_code == 403
    print("PASS: chat-preview requires Bearer token")


def test_chat_preview_uses_owner_channel(monkeypatch):
    """Вызов: include_hidden=True, visitor=admin-preview, ответ проведён наружу."""
    _CAPTURED.clear()
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token-123")
    from app.core.config import get_settings

    get_settings.cache_clear()
    patches = [
        patch("app.services.chat_orchestrator.ChatOrchestrator", FakeOrch),
        patch("app.services.rag.rag_service.RAGService", _fake_rag),
        patch("app.services.execution_tracing_service.ExecutionTracingService"),
    ]
    for p in patches:
        p.start()
    try:
        resp = asyncio.run(cp.chat_preview(
            cp.ChatPreviewRequest(message="расскажи про TAIG"),
            http_request=_fake_request(),
            db=MagicMock(),
            _=None,
        ))
    finally:
        for p in patches:
            p.stop()
        get_settings.cache_clear()
    assert _CAPTURED.get("include_hidden") is True
    kw = _CAPTURED["process_request"]
    assert kw["visitor_id"] == "admin-preview"
    assert kw["user_query"] == "расскажи про TAIG"
    assert resp.answer == "Ответ владельца"
    assert resp.rag_used is True
    assert resp.sources_detail[0]["repo"] == "r"
    print("PASS: chat-preview runs orchestrator with include_hidden=True")


def test_chat_preview_wraps_errors(monkeypatch):
    """Внутреннее исключение → HTTPException 500 с понятным detail."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token-123")
    from app.core.config import get_settings

    get_settings.cache_clear()
    patches = [
        patch("app.services.chat_orchestrator.ChatOrchestrator", BoomOrch),
        patch("app.services.rag.rag_service.RAGService", _fake_rag),
        patch("app.services.execution_tracing_service.ExecutionTracingService"),
    ]
    for p in patches:
        p.start()
    try:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(cp.chat_preview(
                cp.ChatPreviewRequest(message="x"),
                http_request=_fake_request(),
                db=MagicMock(),
                _=None,
            ))
    finally:
        for p in patches:
            p.stop()
        get_settings.cache_clear()
    assert excinfo.value.status_code == 500
    assert "Ошибка обработки запроса чата" in str(excinfo.value.detail)
    print("PASS: chat-preview wraps errors into 500 detail")