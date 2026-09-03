"""
Юнит-тесты защитных правил промпта /case-match (Morphic-проба).

Примечание: TestClient не используется (несовместим httpx в среде тестов) —
эндпойнт вызывается напрямую как async-функция (паттерн test_admin_chat_preview).

Контекст (03.09.2026): дефект why-текста — модель переносила формулировку
задачи зрителя в описание проекта, не подтверждённое карточкой/документами
(TIB «выгрузка в CRM»). Проверяется, что в промпт входит анти-перенос
правило и что валидация выхода отбрасывает чужие слаги и режет «why».
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

import app.api.case_match as cm

_CARDS = [
    SimpleNamespace(
        slug="telegram-intake-bot",
        title="Telegram-бот первичной поддержки",
        short_description="FAQ и сбор лидов",
    ),
    SimpleNamespace(
        slug="review-flow",
        title="Review Flow",
        short_description="AI-обработка заявок",
    ),
]

_ANSWER = (
    '[{"slug": "telegram-intake-bot", "why": "FAQ и сбор лидов, %s"},'
    ' {"slug": "ghost-project", "why": "несуществующий кейс"}]'
) % ("х" * 250)


def _patch_env(captured: dict):
    registry = MagicMock()
    registry.cards = _CARDS
    provider = MagicMock()

    async def generate(prompt, temperature=0.2, max_tokens=500):
        captured["prompt"] = prompt
        return _ANSWER

    provider.generate = generate

    def build_effective_config(row):
        return SimpleNamespace(provider_key="openai", model_name="gpt-4o-mini")

    settings = MagicMock()
    settings.get_active_with_fallback.return_value = (
        SimpleNamespace(provider_key="openai"), None,
    )
    settings.build_effective_config = build_effective_config

    rag = MagicMock()
    rag.search.return_value = [
        SimpleNamespace(
            source="README.md",
            content="контент TIB",
            metadata={"repo": "AlexLvGulyaev/telegram-intake-bot", "path": "README.md"},
        ),
        SimpleNamespace(
            source="docs/BUSINESS_VALUE.md",
            content="контент чужого кейса",
            metadata={"repo": "AlexLvGulyaev/Lead-Qualification-MVP",
                      "path": "docs/BUSINESS_VALUE.md"},
        ),
        SimpleNamespace(source="README.md", content="без метаданных",
                        metadata=None),
    ]

    manager = MagicMock()
    manager.get_backend.return_value = rag

    def _registry_factory(_db):
        return registry

    with patch.object(cm, "PortfolioRegistry", _registry_factory), \
         patch.object(cm, "get_retrieval_manager", lambda: manager), \
         patch.object(cm, "AIProviderSettingsService", lambda db: settings), \
         patch.object(cm, "AIProviderFactory",
                      SimpleNamespace(create=lambda key, config: provider)):
        yield


def test_prompt_contains_no_parroting_rule():
    """Анти-перенос правило входит в промпт подбора."""
    captured: dict = {}
    gen = _patch_env(captured)
    next(gen)
    resp = asyncio.run(cm.case_match(
        cm.CaseMatchRequest(task="нужен бот приёма заявок из Telegram с CRM"),
        db=MagicMock(),
    ))
    prompt = captured["prompt"]
    assert "не переноси в\n  описание проекта" in prompt
    assert "Формулировки задачи зрителя" in prompt
    assert "не утверждай" in prompt
    # подписи фрагментов репозиторием (анти-атрибуция чужих фактов)
    assert "[telegram-intake-bot · README.md]" in prompt
    assert "[Lead-Qualification-MVP · docs/BUSINESS_VALUE.md]" in prompt
    assert "только если фрагмент подписан его репозиторием" in prompt
    # штатные блоки сборки на месте
    assert "Реестр проектов:" in prompt
    assert "telegram-intake-bot" in prompt
    assert "Задача зрителя:" in prompt
    # валидация: чужой слаг отброшен, why обрезан до 200
    assert len(resp.items) == 1
    assert resp.items[0].slug == "telegram-intake-bot"
    assert len(resp.items[0].why) <= 200
    assert resp.provider == "openai"


def test_prompt_rules_kept():
    """Базовые защитные правила промпта сохранены при правке."""
    rules = cm._SYSTEM_RULES
    for marker in (
        "Опирайся только на описания карточек",
        "Не обещай статусов",
        "прямого кейса про",
        "СТРОГО JSON-массивом",
    ):
        assert marker in rules