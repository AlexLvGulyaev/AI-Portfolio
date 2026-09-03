"""
Деградация retrieval-канала: ошибка не роняет запрос с 500.

Замечания PEf01-2/PEf02-2 (ревью Антона, вариант A, решение владельца
03.09.2026): при полном отвалу OpenAI запрос раньше умирал на эмбеддингах
запроса (`rag_service._create_embeddings` без try/except) — GigaChat-фоллбэк
не срабатывал, зритель получал 500 с сырым текстом исключения. Теперь ошибка
retrieval деградирует к генерации без контекста: LLM-failover и честный
отказ в промпте остаются доступны.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tests.test_chat_orchestrator_fixes import _fake_provider, _make_orch


def _run(orch, query="расскажи про HR Assistant"):
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        return asyncio.run(
            orch.process_request(
                user_query=query,
                session_id=None,
                visitor_id=None,
                page_slug=None,
            )
        )


def test_count_documents_failure_degrades_to_answer():
    """Векторная СУБД недоступна (count_documents падает) — запрос
    продолжается в генерацию: ответ есть, retrieval не использовался."""
    orch, rag, _ = _make_orch(memory=[])
    rag.count_documents.side_effect = Exception("chroma connection refused")
    dto = _run(orch)
    assert dto.answer == "Ответ модели"
    assert dto.rag_used is False
    rag.search.assert_not_called()
    print("PASS: count_documents failure degrades to LLM answer")


def test_search_failure_degrades_to_answer():
    """Провайдер эмбеддингов недоступен (search падает) — запрос
    продолжается в генерацию, 500 не возвращается."""
    orch, rag, _ = _make_orch(memory=[])
    rag.search.side_effect = Exception("openai embeddings 503")
    dto = _run(orch)
    assert dto.answer == "Ответ модели"
    assert dto.rag_used is False
    print("PASS: search failure degrades to LLM answer")


def test_search_diverse_failure_degrades_to_answer():
    """Мультипроектный маршрут (search_diverse) тоже деградирует."""
    card_a = SimpleNamespace(slug="review-flow", display_order=1)
    card_b = SimpleNamespace(slug="ai-curator", display_order=2)
    orch, rag, _ = _make_orch(memory=[], registry={
        "resolve_all": lambda q: [card_a, card_b],
        "repo_for_card": lambda c: f"o/{c.slug}",
    })
    rag.search_diverse.side_effect = Exception("openai embeddings 503")
    dto = _run(orch, query="сравни review-flow и AI Curator")
    assert dto.answer == "Ответ модели"
    assert dto.rag_used is False
    print("PASS: search_diverse failure degrades to LLM answer")


def test_degradation_provider_still_used():
    """При деградации retrieval генерация выполняется активным провайдером
    (failover-логика не задета): provider был вызван."""
    orch, rag, _ = _make_orch(memory=[])
    rag.count_documents.side_effect = Exception("chroma down")
    provider = MagicMock()
    calls = []

    async def _gen(prompt, **kwargs):
        calls.append(prompt)
        return "Ответ модели"

    provider.generate.side_effect = _gen
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        dto = asyncio.run(orch.process_request(
            user_query="вопрос", session_id=None, visitor_id=None,
            page_slug=None))
    assert dto.answer == "Ответ модели"
    assert len(calls) == 1
    print("PASS: LLM still called after retrieval degradation")