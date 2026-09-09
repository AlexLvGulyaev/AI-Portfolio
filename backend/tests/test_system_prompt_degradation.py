#!/usr/bin/env python3
"""
Честная деградация канала при недоступности активного промпта
(решение B, план 4a, 09.09.2026).

Покрывает:
1. load_active_prompt → (None, None) → ChatOrchestrator.prompt_unavailable=True
2. process_request поднимает PromptUnavailableError (вшитый v8 НЕ используется)
3. Публичный маршрут /chat маппит ошибку в HTTP 503 с честным сообщением
4. Admin chat-preview маппит в HTTP 503
5. Миграция 025: логика seed'а — idempotent при активной строке
6. reset_to_builtin — явная owner-операция, не fallback
"""

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.admin.system_prompt_service import PromptUnavailableError


def _make_orch():
    """ChatOrchestrator с промптом, недоступным в БД (patch load_active_prompt)."""
    with patch("app.services.chat_orchestrator.ChatSessionService"), \
         patch("app.services.chat_orchestrator.ConversationMemoryService"), \
         patch("app.services.chat_orchestrator.AIProviderSettingsService"), \
         patch("app.services.chat_orchestrator.OperationalLogService"), \
         patch("app.services.portfolio_registry.PortfolioRegistry"), \
         patch("app.services.chat_orchestrator.PromptAssembly"), \
         patch(
             "app.services.admin.system_prompt_service.load_active_prompt",
             return_value=(None, None),
         ):
        from app.services.chat_orchestrator import ChatOrchestrator

        orch = ChatOrchestrator(
            db=MagicMock(),
            cache=MagicMock(),
            rag_service=MagicMock(),
            tracing_service=MagicMock(),
        )
    return orch


def test_orchestrator_marks_prompt_unavailable():
    orch = _make_orch()
    assert orch.prompt_unavailable is True
    assert orch.prompt_assembly is None


def test_process_request_raises_prompt_unavailable():
    orch = _make_orch()
    with pytest.raises(PromptUnavailableError):
        asyncio.run(orch.process_request(
            user_query="тест", visitor_id="v-degr", client_ip="t", user_agent="t"
        ))


def test_public_chat_route_maps_to_503():
    import asyncio

    from app.api.chat import chat as chat_route

    orch = _make_orch()
    request = SimpleNamespace(
        message="тест", session_id=None, visitor_id="v", page_slug=None
    )
    http_request = MagicMock()
    http_request.headers = {"user-agent": "t"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat_route(
            request=request, http_request=http_request, orchestrator=orch
        ))
    assert exc.value.status_code == 503
    assert "недоступен" in exc.value.detail


def test_admin_preview_maps_to_503():
    """Канал владельца: PromptUnavailableError → HTTP 503 (паттерн suite)."""
    import asyncio

    import app.api.admin.chat_preview as cp
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkey = {"token": True}

    class DegradOrch:
        def __init__(self, **kwargs):
            pass

        async def process_request(self, **kw):
            raise PromptUnavailableError("no active prompt")

    def _fake_rag(config):
        svc = MagicMock()
        svc.config = SimpleNamespace(collection_name="c")
        return svc

    patches = [
        patch("app.services.chat_orchestrator.ChatOrchestrator", DegradOrch),
        patch("app.services.rag.rag_service.RAGService", _fake_rag),
        patch("app.services.execution_tracing_service.ExecutionTracingService"),
    ]
    for p in patches:
        p.start()
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(cp.chat_preview(
                cp.ChatPreviewRequest(message="x"),
                http_request=MagicMock(),
                db=MagicMock(),
                _=None,
            ))
    finally:
        for p in patches:
            p.stop()
        get_settings.cache_clear()
    assert exc.value.status_code == 503
    assert "недоступен" in exc.value.detail


def test_seed_migration_noop_when_active_exists():
    """Идемпотентность 025: при активной строке ничего не вставляется."""
    import sqlalchemy as sa

    conn = MagicMock()
    probe = MagicMock()
    probe.first.return_value = ("some-id",)
    conn.execute.return_value = probe
    with patch("alembic.op.get_bind", return_value=conn):
        spec = importlib.util.spec_from_file_location(
            "m025",
            str(backend_path / "migrations" / "versions" / "025_seed_builtin_prompt.py"),
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.upgrade()
    # UPDATE/INSERT не вызывались — только SELECT активной строки
    assert conn.execute.call_count == 1


def test_seed_migration_inserts_when_table_empty():
    """Seed: пустая таблица → вставляется активный вшитый базлайн."""
    import sqlalchemy as sa

    from app.services.prompt_assembly import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION

    conn = MagicMock()
    probe = MagicMock()
    probe.first.return_value = None  # нет активной строки
    conn.execute.return_value = probe
    with patch("alembic.op.get_bind", return_value=conn):
        spec = importlib.util.spec_from_file_location(
            "m025b",
            str(backend_path / "migrations" / "versions" / "025_seed_builtin_prompt.py"),
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.upgrade()
    # SELECT активной строки + SELECT существующей пары + INSERT
    assert conn.execute.call_count == 3
    sql = str(conn.execute.call_args[0][0])
    params = conn.execute.call_args[0][1]  # второй позиционный аргумент
    assert "INSERT INTO system_prompts" in sql
    assert params["v"] == SYSTEM_PROMPT_VERSION
    assert params["b"] == SYSTEM_PROMPT


def test_builtin_still_usable_via_reset_to_builtin():
    """Сброс к вшитому — явная owner-операция через консоль, не fallback."""
    from app.services.admin.system_prompt_service import SystemPromptService
    from app.services.prompt_assembly import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION

    db = MagicMock()
    # нет существующей пары версия+hash → создаётся новая строка
    db.scalar.return_value = None
    svc = SystemPromptService(db)
    svc._activate_row = MagicMock(return_value={"version": SYSTEM_PROMPT_VERSION})
    result = svc.reset_to_builtin()
    assert result["version"] == SYSTEM_PROMPT_VERSION
    added = db.add.call_args[0][0]
    assert added.body == SYSTEM_PROMPT
    assert added.is_builtin is True
    # активация выполняется _activate_row (единый путь активации)
    svc._activate_row.assert_called_once_with(added)