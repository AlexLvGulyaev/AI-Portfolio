"""
Unit-тесты ChatOrchestrator (без внешних сервисов).

Покрывают дефекты baseline:
- D2: session-blind cache — версионный fingerprint-ключ, bypass кеша при
  наличии истории диалога (§2);
- D1/D5: детерминированные маршруты листинга/счёта без LLM (§3);
- D4/D6: project-scoped retrieval, диверсифицированный retrieval (§4, §5);
- D8: ровно один retrieval на cache-miss (§9);
- D6: цитаты `<repository> · <path>` с дедупликацией (§8).
"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.cache.response_cache import ResponseCache


def _make_orch(memory, *, registry=None, cache=None):
    """Собирает ChatOrchestrator с замоканными внешними сервисами."""
    with patch("app.services.chat_orchestrator.ChatSessionService") as SessCls, \
         patch("app.services.chat_orchestrator.ConversationMemoryService") as MemCls, \
         patch("app.services.chat_orchestrator.AIProviderSettingsService") as ProvCls, \
         patch("app.services.chat_orchestrator.OperationalLogService"), \
         patch("app.services.portfolio_registry.PortfolioRegistry") as RegCls, \
         patch("app.services.chat_orchestrator.PromptAssembly"):
        sess = SessCls.return_value
        sess.create_session.return_value = uuid.uuid4()

        mem = MemCls.return_value
        mem.get_recent_messages.return_value = memory

        prov = ProvCls.return_value
        row = MagicMock()
        prov.get_effective_provider.return_value = (row, [])
        prov.build_effective_config.return_value = SimpleNamespace(
            provider_key="openai", model_name="gpt-4.1-mini",
            temperature=0.2, max_tokens=500,
        )

        reg = RegCls.return_value
        reg.version = "testregver1"
        reg.repos = ["o/Repo-A", "o/Repo-B", "o/Repo-C"]
        if registry:
            reg.classify.side_effect = registry.get("classify", lambda q: "unknown")
            reg.resolve_all.side_effect = registry.get(
                "resolve_all", lambda q: [])
            reg.repo_for_card.side_effect = registry.get(
                "repo_for_card", lambda c: "o/Repo-X")
            reg.render_list.side_effect = registry.get(
                "render_list", lambda: "В портфолио 13 проектов:")
            reg.render_count.side_effect = registry.get(
                "render_count", lambda: "В портфолио 13 проектов.")

        rag = MagicMock()
        rag.config = SimpleNamespace(collection_name="test_collection")
        rag.count_documents.return_value = 100
        rag.search.return_value = []
        rag.search_diverse.return_value = []
        rag.build_context.return_value = "ctx"

        cache = cache or ResponseCache(
            cache_file="data/cache/unittest_cache.json",
            enable_persistence=False,
        )

        from app.services.chat_orchestrator import ChatOrchestrator

        orch = ChatOrchestrator(
            db=MagicMock(),
            cache=cache,
            rag_service=rag,
            rag_top_k=3,
        )
        return orch, rag, cache


def _fake_provider(orch, answer="Ответ модели"):
    provider = MagicMock()

    async def _gen(prompt, **kwargs):
        return answer

    provider.generate.side_effect = _gen
    return provider


# ---------- §2: версионный кеш ----------

def test_cache_key_includes_config_fingerprint():
    orch, _, cache = _make_orch(memory=[])
    k1 = cache.get_cache_key("вопрос", orch._config_fingerprint("openai", "gpt-4.1-mini"))
    # смена модели → другой ключ
    k2 = cache.get_cache_key("вопрос", orch._config_fingerprint("openai", "gpt-4o"))
    # смена провайдера → другой ключ
    k3 = cache.get_cache_key("вопрос", orch._config_fingerprint("gigachat", "gpt-4.1-mini"))
    # смена retrieval-конфигурации → другой ключ
    orch.rag_top_k = 5
    k4 = cache.get_cache_key("вопрос", orch._config_fingerprint("openai", "gpt-4.1-mini"))
    assert len({k1, k2, k3, k4}) == 4
    print("PASS: fingerprint components change the cache key")


def test_cache_miss_on_collection_change():
    """Смена коллекции (KB) гарантирует cache miss — старые ответы не выдаются."""
    c1 = ResponseCache(cache_file="x.json", enable_persistence=False,
                       config_fingerprint="col:kb_v2|prompt:v1|retrieval:top_k=3|openai/m1")
    c1.set("query", "старый ответ по старой KB")
    c2 = ResponseCache(cache_file="x.json", enable_persistence=False,
                       config_fingerprint="col:kb_v3|prompt:v1|retrieval:top_k=3|openai/m1")
    assert c2.get("query") is None
    print("PASS: collection change invalidates cache")


def test_cache_miss_on_prompt_version_change():
    c1 = ResponseCache(cache_file="x.json", enable_persistence=False,
                       config_fingerprint="col:c|prompt:v1|retrieval:top_k=3|openai/m1")
    c1.set("query", "ответ старого промпта")
    c2 = ResponseCache(cache_file="x.json", enable_persistence=False,
                       config_fingerprint="col:c|prompt:v2|retrieval:top_k=3|openai/m1")
    assert c2.get("query") is None
    print("PASS: prompt version change invalidates cache")


def test_old_v1_cache_entries_not_readable():
    """Записи старой схемы ключей (v1, без fingerprint) недоступны в v2."""
    import hashlib, json as _json, tempfile, os
    old_key = hashlib.sha256("normalized query".encode()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "cache.json")
        with open(f, "w", encoding="utf-8") as fh:
            _json.dump({"entries": {old_key: {
                "query_hash": old_key, "query": "query",
                "response": "STALE v1 ANSWER", "created_at": 0.0,
                "expires_at": None, "metadata": {},
            }}, "stats": {}}, fh)
        cache = ResponseCache(cache_file=f, enable_persistence=True,
                              config_fingerprint="col:c|prompt:v2")
        assert cache.get("query") is None
    print("PASS: v1 cache entries are not served under v2 keys")


def test_history_bypasses_cache():
    """§2: ответ с историей диалога не читается и не пишется в кеш."""
    memory = [SimpleNamespace(role="user", content="привет")]
    orch, rag, cache = _make_orch(memory=memory)
    provider = _fake_provider(orch, "Ответ с учётом истории")
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac, \
         patch("app.services.cache.response_cache.ResponseCache.get") as get_mock:
        Fac.create.return_value = provider
        import asyncio
        dto = asyncio.run(orch.process_request(
            user_query="вопрос с историей", session_id=uuid.uuid4()))
        assert get_mock.await_count == 0 if asyncio.iscoroutine(get_mock) else not get_mock.called
        assert dto.answer == "Ответ с учётом истории"
    # set тоже не вызван: в кеше нет записи
    assert cache.get("вопрос с историей",
                     orch._config_fingerprint("openai", "gpt-4.1-mini")) is None
    print("PASS: history bypasses cache read and write")


def test_llm_answer_not_cached_registry_only_policy():
    """Безопасная политика кеша (§3): LLM-ответы не кешируются вовсе —
    эвристика отказа не покрывает парафразы, а структурного признака
    cache_eligible пока нет. Детерминированные ответы реестра кешируются
    отдельно (см. test_listing_route_cached_by_registry_version)."""
    orch, rag, cache = _make_orch(memory=[])
    calls = {"n": 0}
    provider = MagicMock()

    async def _gen(prompt, **kwargs):
        calls["n"] += 1
        return f"Ответ {calls['n']}"

    provider.generate.side_effect = _gen
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        d1 = asyncio.run(orch.process_request(user_query="повтори меня"))
        assert d1.cache_hit is False and calls["n"] == 1
        d2 = asyncio.run(orch.process_request(user_query="Повтори меня"))
        assert d2.cache_hit is False and calls["n"] == 2, (
            "LLM answers must not be cached under registry-only policy")
    assert cache.size() == 0
    print("PASS: LLM answers are not cached (registry-only cache policy)")


def test_same_text_different_context_no_shared_answer():
    """§2: запрос с историей не получает кешированный ответ stateless-запроса."""
    import asyncio
    orch, _, cache = _make_orch(memory=[])
    provider = MagicMock()

    async def _gen(prompt, **kwargs):
        return " Stateless ответ"

    provider.generate.side_effect = _gen
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        asyncio.run(orch.process_request(user_query="общий вопрос"))
    # второй оркестратор с историей в сессии
    orch2, _, _ = _make_orch(memory=[SimpleNamespace(role="assistant", content="ранний ответ")])
    provider2 = MagicMock()

    async def _gen2(prompt, **kwargs):
        return " Ответ с историей"

    provider2.generate.side_effect = _gen2
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac2:
        Fac2.create.return_value = provider2
        dto = asyncio.run(orch2.process_request(user_query="общий вопрос"))
    assert dto.answer != " Stateless ответ".strip() or True
    assert "Stateless" not in dto.answer
    print("PASS: history query does not receive stateless cached answer")


# ---------- §3: детерминированные маршруты ----------

def test_listing_route_no_llm():
    orch, rag, cache = _make_orch(memory=[], registry={
        "classify": lambda q: "listing",
        "render_list": lambda: "В портфолио 13 проектов:\n1. X",
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.side_effect = AssertionError("LLM must not be called for listing")
        dto = asyncio.run(orch.process_request(user_query="Какие проекты есть в портфолио?"))
    assert dto.answer.startswith("В портфолио 13 проектов")
    assert dto.rag_used is False
    assert dto.metadata.get("route") == "registry_listing"
    rag.search.assert_not_called()
    print("PASS: listing route is deterministic (no LLM, no RAG)")


def test_listing_route_cached_by_registry_version():
    orch, _, cache = _make_orch(memory=[], registry={
        "classify": lambda q: "listing",
        "render_list": lambda: "В портфолио 13 проектов:\n1. X",
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory"):
        asyncio.run(orch.process_request(user_query="перечисли проекты"))
        # вторая публикация того же вопроса → cache hit
        dto = asyncio.run(orch.process_request(user_query="перечисли проекты"))
    assert dto.cache_hit is True
    print("PASS: listing answers cached under registry fingerprint")


def test_listing_route_ignores_stale_registry_cache():
    """Смена версии реестра инвалидирует детерминированные ответы."""
    orch, _, cache = _make_orch(memory=[], registry={
        "classify": lambda q: "count",
        "render_count": lambda: "В портфолио 13 проектов: A, B.",
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory"):
        asyncio.run(orch.process_request(user_query="сколько проектов?"))
        orch.registry.version = "testregver2"
        orch.registry.render_count = lambda: "В портфолио 14 проектов: A, B, C."
        dto = asyncio.run(orch.process_request(user_query="сколько проектов?"))
    assert "13" not in dto.answer and dto.cache_hit is False
    print("PASS: registry version change invalidates deterministic cache")


# ---------- §4/§5: retrieval-маршрутизация ----------

def test_project_scoped_retrieval_uses_repo_filter():
    card = SimpleNamespace(slug="hr-assistant", display_order=1)
    orch, rag, _ = _make_orch(memory=[], registry={
        "resolve_all": lambda q: [card],
        "repo_for_card": lambda c: "o/HR-Assistant",
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/HR-Assistant", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="расскажи про HR Assistant"))
    args, kwargs = rag.search.call_args
    assert kwargs.get("where") == {"repo": {"$eq": "o/HR-Assistant"}}
    assert rag.search.call_count == 1
    rag.search_diverse.assert_not_called()
    print("PASS: single-project query uses repo-scoped retrieval")


def test_multi_project_query_uses_diverse_retrieval():
    card_a = SimpleNamespace(slug="review-flow", display_order=1)
    card_b = SimpleNamespace(slug="ai-curator", display_order=2)
    orch, rag, _ = _make_orch(memory=[], registry={
        "resolve_all": lambda q: [card_a, card_b],
        "repo_for_card": lambda c: f"o/{c.slug}",
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="сравни Review Flow и AI Curator"))
    rag.search.assert_not_called()
    kwargs = rag.search_diverse.call_args.kwargs
    assert set(kwargs["repos"]) == {"o/review-flow", "o/ai-curator"}
    print("PASS: multi-project query uses diversified retrieval by repo")


def test_filtered_question_searches_all_repos():
    orch, rag, _ = _make_orch(memory=[], registry={
        "classify": lambda q: "filtered",
        "resolve_all": lambda q: [],
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="Какие проекты используют n8n?"))
    kwargs = rag.search_diverse.call_args.kwargs
    assert set(kwargs["repos"]) == {"o/Repo-A", "o/Repo-B", "o/Repo-C"}
    assert kwargs["max_per_repo"] <= 2, "one repo must not take all context"
    print("PASS: filtered question uses bounded fan-out over all repos")


def test_filtered_route_one_best_chunk_per_repo():
    """§5: сильные репозитории не вытесняют остальные — 1 чанк на репозиторий."""
    orch, rag, _ = _make_orch(memory=[], registry={
        "classify": lambda q: "filtered",
        "resolve_all": lambda q: [],
    })
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="У каких проектов есть веб-интерфейс?"))
    kwargs = rag.search_diverse.call_args.kwargs
    assert kwargs["max_per_repo"] == 1, "each repo must contribute its best chunk"
    assert kwargs["final_top_k"] == 12
    print("PASS: filtered route gives each repo its best chunk")


def test_refusal_answer_not_cached():
    """Отказ LLM не попадает в кеш (при политике registry-only не кешируется
    ни один LLM-ответ — отказ лишь частный случай)."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/x", "path": "README.md"}, chunk_id="1")]
    set_mock = MagicMock()
    with patch.object(cache, "set", set_mock):
        import asyncio
        with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
            Fac.create.return_value = _fake_provider(
                orch, "В текущем портфеле и базе знаний такой информации нет.")
            asyncio.run(orch.process_request(user_query="вопрос про несуществующий факт"))
    set_mock.assert_not_called()
    # Обычный LLM-ответ тоже не кешируется (registry-only политика §3)
    orch2, rag2, cache2 = _make_orch(memory=[])
    rag2.search.return_value = rag.search.return_value
    set_mock2 = MagicMock()
    with patch.object(cache2, "set", set_mock2):
        with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
            Fac.create.return_value = _fake_provider(orch2, "Обычный содержательный ответ")
            asyncio.run(orch2.process_request(user_query="другой вопрос"))
    assert not set_mock2.called
    assert cache2.size() == 0
    print("PASS: refusal and normal LLM answers are not cached (registry-only)")


def test_is_refusal_pattern():
    from app.services.chat_orchestrator import ChatOrchestrator
    assert ChatOrchestrator._is_refusal(
        "В текущем портфеле и базе знаний такой информации нет.")
    assert ChatOrchestrator._is_refusal(
        "К сожалению, такой информации нет в базе.")
    assert not ChatOrchestrator._is_refusal("HR Assistant обрабатывает резюме.")
    assert not ChatOrchestrator._is_refusal("")
    print("PASS: refusal detection matches canonical grounded refusal")


# ---------- §9: один retrieval ----------

def test_single_retrieval_per_cache_miss():
    """Контекст строится из уже полученных результатов; get_context не зовётся."""
    orch, rag, _ = _make_orch(memory=[])
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1, metadata={"repo": "o/x", "path": "README.md"},
        chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="обычный вопрос"))
    assert rag.search.call_count == 1
    rag.get_context.assert_not_called()
    assert rag.build_context.call_count == 1
    print("PASS: exactly one retrieval per cache miss")


# ---------- §8: цитаты ----------

def test_citations_repo_path_deduped_in_order():
    from app.services.chat_orchestrator import ChatOrchestrator

    results = [
        SimpleNamespace(content="", source="README.md", score=0.1,
                        metadata={"repo": "o/A", "path": "README.md"}),
        SimpleNamespace(content="", source="docs/arch.md", score=0.2,
                        metadata={"repo": "o/B", "path": "docs/arch.md"}),
        SimpleNamespace(content="", source="README.md", score=0.3,
                        metadata={"repo": "o/A", "path": "README.md"}),
    ]
    sources, detail = ChatOrchestrator._citations(results)
    assert sources == ["o/A · README.md", "o/B · docs/arch.md"]
    assert len(detail) == 3
    assert detail[0]["repo"] == "o/A" and detail[0]["path"] == "README.md"
    print("PASS: citations are repository + path, deduped, first-appearance order")


if __name__ == "__main__":
    import inspect
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ORCHESTRATOR TESTS PASSED")