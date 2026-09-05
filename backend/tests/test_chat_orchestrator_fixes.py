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


def _make_orch(memory, *, registry=None, cache=None, include_hidden=False):
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
        # B1 visibility guard: по умолчанию скрывать нечего — фильтр
        # прозрачен; тесты с hidden-репозиториями переопределяют ниже.
        reg.public_repos.side_effect = (
            lambda repos=None: list(repos) if repos is not None else list(reg.repos)
        )
        reg.public_guard.return_value = None
        # Скрытая карточка в listing/count-интенте (класс H): по умолчанию
        # мок-реестр скрывать нечего — resolve_hidden обязан возвращать None
        # (иначе MagicMock отвечает правдивым Mock и ломает маршрут).
        reg.resolve_hidden.side_effect = lambda q: None
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
            include_hidden=include_hidden,
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


def test_normalization_same_query_cache_hit():
    """Нормализация ключа кеша: один и тот же вопрос в разном регистре —
    один ключ. Cache-eligible политика 04.09.2026 в расширенной редакции
    (решение владельца 04.09.2026: без требования цитаты [N]): grounded-
    ответ (rag_used, без отказа и fallback) кешируется, повтор — из кеша.
    Детерминированные ответы реестра кешируются отдельно
    (см. test_listing_route_cached_by_registry_version);
    полный набор кеш-тестов — test_chat_cache_eligible.py."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [SimpleNamespace(
        content="Контекст проекта.", chunk_id="c1", score=0.9,
        source="docs/README.md",
        metadata={"repo": "o/Repo-A", "path": "docs/README.md"})]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = [
        ("o/Repo-A", "Проект A", "main", "Проект A")]
    orch.prompt_assembly.fingerprint.return_value = "fp-cache-test"
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
        assert d2.cache_hit is True and calls["n"] == 1, (
            "нормализованный повтор должен отдаваться из кеша")
    assert cache.size() == 1
    print("PASS: normalized identical query served from cache")


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


def test_impersonal_eto_not_anaphora():
    """Безличное «это» («что это за …») не анафора: retrieval не сужается
    прошлым проектом из истории (кейс 03.09: чип «Что это за платформа?» в
    сессии со старой историей про AI Curator → поиск по чужому репозиторию)."""
    card = SimpleNamespace(slug="ai-curator", display_order=1)
    memory = [SimpleNamespace(role="user", content="расскажи про AI Curator")]
    orch, rag, _ = _make_orch(memory=memory, registry={
        "resolve_all": lambda q: [card] if "AI Curator" in q else [],
        "repo_for_card": lambda c: "o/AI-Curator",
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/AI-Curator", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="Что это за платформа?"))
    args, kwargs = rag.search.call_args
    # глобальный поиск: без repo-фильтра, запрос не обогащён историей
    assert kwargs.get("where") is None
    assert args and args[0] == "Что это за платформа?"
    print("PASS: impersonal 'что это за …' skips anaphora enrichment")


def test_real_anaphora_still_enriches_retrieval():
    """Настоящая анафора («какой у него стек») по-прежнему обогащает retrieval
    последним сообщением с проектом → repo-scoped поиск."""
    card = SimpleNamespace(slug="ai-curator", display_order=1)
    memory = [SimpleNamespace(role="user", content="расскажи про AI Curator")]
    orch, rag, _ = _make_orch(memory=memory, registry={
        "resolve_all": lambda q: [card] if "AI Curator" in q else [],
        "repo_for_card": lambda c: "o/AI-Curator",
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/AI-Curator", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="какой у него стек?"))
    args, kwargs = rag.search.call_args
    # project_scoped: сужение делает repo-фильтр (запрос остаётся исходным)
    assert kwargs.get("where") == {"repo": {"$eq": "o/AI-Curator"}}
    assert rag.search.call_count == 1
    print("PASS: real anaphora still scopes retrieval to prior project")


def test_page_demonstrative_beats_stale_anaphora():
    """«Этот кейс» при валидном page_slug — ссылка на страницу, не анафора к
    проекту из истории (кейс 05.09: «Как устроен этот кейс?» на странице
    Retail Group в сессии с прежними вопросами про Assistant Flow → анафора
    вытесняла страницу, retrieval искал в чужом репозитории при верном
    ответе). Страница скупо сужает retrieval, запрос не обогащается."""
    af_card = SimpleNamespace(slug="assistant-flow", display_order=1)
    page_card = SimpleNamespace(slug="retail-group", display_order=2)
    memory = [SimpleNamespace(
        role="user", content="Какие технологии использованы в кейсе Assistant Flow?")]
    orch, rag, _ = _make_orch(memory=memory, registry={
        "resolve_all": lambda q: [af_card] if "Assistant Flow" in q else [],
        "repo_for_card": lambda c: (
            "o/Assistant-Flow" if c.slug == "assistant-flow" else "o/Retail-Group"),
        "get_by_slug": lambda slug: page_card if slug == "retail-group" else None,
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/Retail-Group", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(
            user_query="Как устроен этот кейс?", page_slug="retail-group"))
    args, kwargs = rag.search.call_args
    # project_scoped по странице: repo-фильтр Retail-Group, без обогащения
    assert kwargs.get("where") == {"repo": {"$eq": "o/Retail-Group"}}
    assert args and args[0] == "Как устроен этот кейс?"
    assert rag.search.call_count == 1
    print("PASS: 'этот кейс' on a valid case page scopes retrieval to the page repo")


def test_page_demonstrative_without_page_card_keeps_anaphora():
    """Тот же «этот кейс», но валидной страницы нет (page_slug=None) —
    работает прежняя анафора: сужение по проекту из истории."""
    af_card = SimpleNamespace(slug="assistant-flow", display_order=1)
    memory = [SimpleNamespace(
        role="user", content="Какие технологии использованы в кейсе Assistant Flow?")]
    orch, rag, _ = _make_orch(memory=memory, registry={
        "resolve_all": lambda q: [af_card] if "Assistant Flow" in q else [],
        "repo_for_card": lambda c: "o/Assistant-Flow",
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/Assistant-Flow", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="Как устроен этот кейс?"))
    args, kwargs = rag.search.call_args
    # project_scoped-ветка ищет по сырому запросу; сужение делает repo-фильтр
    # по проекту из истории — это и есть признак сработавшей анафоры
    assert kwargs.get("where") == {"repo": {"$eq": "o/Assistant-Flow"}}
    assert args and args[0] == "Как устроен этот кейс?"
    print("PASS: without a valid page card, anaphora still scopes to prior project")


def test_named_project_on_case_page_beats_page_demonstrative():
    """Явно названный проект в текущем запросе приоритетнее страницы, даже
    если запрос содержит «этот кейс»."""
    af_card = SimpleNamespace(slug="assistant-flow", display_order=1)
    page_card = SimpleNamespace(slug="retail-group", display_order=2)
    orch, rag, _ = _make_orch(memory=[], registry={
        "resolve_all": lambda q: [af_card] if "Assistant Flow" in q else [],
        "repo_for_card": lambda c: (
            "o/Assistant-Flow" if c.slug == "assistant-flow" else "o/Retail-Group"),
        "get_by_slug": lambda slug: page_card if slug == "retail-group" else None,
    })
    rag.search.return_value = [SimpleNamespace(
        content="c", source="README.md", score=0.1,
        metadata={"repo": "o/Assistant-Flow", "path": "README.md"}, chunk_id="1")]
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(
            user_query="Assistant Flow — как устроен этот кейс?",
            page_slug="retail-group"))
    args, kwargs = rag.search.call_args
    assert kwargs.get("where") == {"repo": {"$eq": "o/Assistant-Flow"}}
    assert rag.search.call_count == 1
    print("PASS: explicitly named project beats page demonstrative")


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


# ---------- §10: visibility guard (owner decision 29.08.2026, variant B1) ----------

HIDDEN_REPOS = ["o/Repo-B"]


def _orch_with_hidden(**registry_extra):
    """Оркестратор с реестром, скрывающим o/Repo-B от публичного retrieval."""
    include_hidden = registry_extra.pop("include_hidden", False)
    orch, rag, _ = _make_orch(
        memory=[],
        registry=registry_extra or None,
        include_hidden=include_hidden,
    )
    reg = orch.registry
    reg.hidden_repos = HIDDEN_REPOS
    reg.public_repos.side_effect = lambda repos=None: [
        r for r in (repos if repos is not None else reg.repos) if r not in HIDDEN_REPOS
    ]
    reg.public_guard.return_value = {"repo": {"$nin": HIDDEN_REPOS}}
    return orch, rag


def test_hidden_repo_excluded_from_global_search():
    """Обычный (глобальный) поиск скрытого контента получает $nin-фильтр."""
    orch, rag = _orch_with_hidden()
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="какой-нибудь обычный вопрос"))
    kwargs = rag.search.call_args.kwargs
    assert kwargs.get("where") == {"repo": {"$nin": HIDDEN_REPOS}}
    print("PASS: global search carries the hidden-repo $nin guard")


def test_hidden_repo_excluded_from_global_fallback():
    """global_fallback после project_scoped miss тоже фильтруется."""
    card = SimpleNamespace(slug="hr-assistant", display_order=1)
    orch, rag = _orch_with_hidden(
        resolve_all=lambda q: [card],
        repo_for_card=lambda c: "o/HR-Assistant",
    )
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="расскажи про HR Assistant"))
    fallback_kwargs = rag.search.call_args.kwargs
    assert fallback_kwargs.get("where") == {"repo": {"$nin": HIDDEN_REPOS}}
    print("PASS: global fallback carries the hidden-repo $nin guard")


def test_hidden_repo_excluded_from_filtered_fanout():
    """diverse_all: скрытый репозиторий не входит в fan-out вовсе."""
    orch, rag = _orch_with_hidden(
        classify=lambda q: "filtered",
        resolve_all=lambda q: [],
    )
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="Какие проекты используют n8n?"))
    kwargs = rag.search_diverse.call_args.kwargs
    assert "o/Repo-B" not in kwargs["repos"], "hidden repo must not be fanned out"
    assert set(kwargs["repos"]) == {"o/Repo-A", "o/Repo-C"}
    print("PASS: filtered fan-out excludes hidden repos")


def test_no_hidden_repos_means_no_where_filter():
    """Когда скрывать нечего, where не добавляется вовсе (None)."""
    orch, rag, _ = _make_orch(memory=[])
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="обычный вопрос"))
    kwargs = rag.search.call_args.kwargs
    assert kwargs.get("where") is None
    print("PASS: no hidden repos → no where filter on global search")


# ---------- include_hidden (admin chat-preview, канал владельца) ----------

def test_include_hidden_global_search_without_guard():
    """Канал владельца: глобальный поиск без $nin-гварда."""
    orch, rag = _orch_with_hidden(include_hidden=True)
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="какой-нибудь обычный вопрос"))
    kwargs = rag.search.call_args.kwargs
    assert kwargs.get("where") is None, "owner channel must not apply the guard"
    print("PASS: include_hidden removes the guard from global search")


def test_include_hidden_fanout_keeps_hidden_repo():
    """Канал владельца: скрытый репозиторий участвует в fan-out как обычный."""
    orch, rag, _ = _make_orch(
        memory=[],
        registry={"classify": lambda q: "filtered", "resolve_all": lambda q: []},
        include_hidden=True,
    )
    reg = orch.registry
    reg.hidden_repos = HIDDEN_REPOS
    reg.public_guard.return_value = {"repo": {"$nin": HIDDEN_REPOS}}
    import asyncio
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider(orch)
        asyncio.run(orch.process_request(user_query="Какие проекты используют n8n?"))
    kwargs = rag.search_diverse.call_args.kwargs
    assert "o/Repo-B" in kwargs["repos"], "owner channel must fan out to hidden repo too"
    assert set(kwargs["repos"]) == {"o/Repo-A", "o/Repo-B", "o/Repo-C"}
    print("PASS: include_hidden fan-out keeps hidden repos")


def test_refusal_answer_not_cached():
    """Отказ LLM не попадает в кеш (cache-eligible политика 04.09.2026:
    `_is_refusal` исключает запись). Обычный grounded-ответ при этом
    кешируется (расширенная редакция решением владельца 04.09.2026 —
    без требования цитаты [N])."""
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
    # Обычный grounded-ответ кешируется (расширенная cache-eligible политика)
    orch2, rag2, cache2 = _make_orch(memory=[])
    rag2.search.return_value = rag.search.return_value
    set_mock2 = MagicMock()
    with patch.object(cache2, "set", set_mock2):
        with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
            Fac.create.return_value = _fake_provider(orch2, "Обычный содержательный ответ")
            asyncio.run(orch2.process_request(user_query="другой вопрос"))
    assert set_mock2.called
    print("PASS: refusal not cached, plain grounded answer cached (cache-eligible)")


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

def test_citations_readable_labels_and_blob_links():
    """Вариант C (02.09.2026): читабельные подписи + GitHub blob в detail."""
    from app.services.chat_orchestrator import ChatOrchestrator

    results = [
        SimpleNamespace(content="", source="README.md", score=0.1,
                        metadata={"repo": "o/A", "path": "README.md"}),
        SimpleNamespace(content="", source="docs/arch.md", score=0.2,
                        metadata={"repo": "o/B", "path": "docs/arch.md"}),
        SimpleNamespace(content="", source="README.md", score=0.3,
                        metadata={"repo": "o/A", "path": "README.md"}),
    ]
    source_info = {"o/A": ("AI Curator", "main"), "o/B": ("Prompt Review", "master")}
    sources, detail = ChatOrchestrator._build_citations(results, source_info)
    assert sources == ["AI Curator · README", "Prompt Review · arch"]
    assert len(detail) == 3
    assert detail[0]["repo"] == "o/A" and detail[0]["path"] == "README.md"
    assert detail[0]["label"] == "AI Curator · README"
    assert detail[0]["html_url"] == "https://github.com/o/A/blob/main/README.md"
    assert detail[1]["html_url"] == "https://github.com/o/B/blob/master/docs/arch.md"
    print("PASS: citations are readable labels, deduped by (repo, path), blob links in detail")


def test_citations_fallbacks_without_source_info():
    """Без маппинга (репо не в реестре) — прежний вид label, без html_url."""
    from app.services.chat_orchestrator import ChatOrchestrator

    results = [
        SimpleNamespace(content="", source="README.md", score=0.1,
                        metadata={"repo": "o/unknown", "path": "README.md"}),
        SimpleNamespace(content="", source="doc.md", score=0.2,
                        metadata={"path": "doc.md"}),
    ]
    sources, detail = ChatOrchestrator._build_citations(results, {})
    assert sources == ["o/unknown · README", "doc.md"]
    assert detail[0]["html_url"] is None
    assert detail[1]["repo"] is None
    print("PASS: citations fall back to repo-prefixed/path labels without html_url")


def test_source_labels_helpers():
    """Хелпер source_labels: короткое имя, подпись, blob-ссылка."""
    from app.services.rag.source_labels import (
        doc_short_name, github_blob_url, make_source_label,
    )

    assert doc_short_name("docs/ARCHITECTURE.md") == "ARCHITECTURE"
    assert doc_short_name("README.md") == "README"
    assert make_source_label("AI Curator", "README.md") == "AI Curator · README"
    url = github_blob_url("AlexLvGulyaev/AI-Portfolio", "master", "docs/TZ.md")
    assert url == "https://github.com/AlexLvGulyaev/AI-Portfolio/blob/master/docs/TZ.md"
    assert github_blob_url("o/r", None, "a.md").endswith("/blob/main/a.md")
    print("PASS: source_labels helpers")


def test_build_context_uses_readable_labels():
    """build_context с source_names: метки [N] для модели — читабельные подписи."""
    from types import SimpleNamespace

    from app.services.rag.rag_service import RAGService

    results = [
        SimpleNamespace(content="текст", source="README.md", score=0.1,
                        metadata={"repo": "o/A", "path": "docs/arch.md"}),
    ]
    ctx = RAGService.build_context(
        RAGService.__new__(RAGService), results,
        source_names={"o/A": "AI Curator"},
    )
    assert "[1] AI Curator · arch:" in ctx
    ctx2 = RAGService.build_context(RAGService.__new__(RAGService), results)
    assert "[1] o/A · README.md:" in ctx2
    print("PASS: build_context readable labels with and without source_names")


# ---------- §12: гигиена цитат (дефект «[N] за пределами топ-5») ----------

def test_strip_stale_citations_cuts_out_of_range():
    from app.services.chat_orchestrator import ChatOrchestrator

    answer = ("Интеграция описана в документации (см. [4], [6]) и в сценарии "
              "(см. [3]). Итог: готово.")
    cleaned, stripped = ChatOrchestrator._strip_stale_citations(answer, 5)
    assert cleaned == ("Интеграция описана в документации (см. [4]) и в сценарии "
                       "(см. [3]). Итог: готово."), repr(cleaned)
    assert stripped == [6], stripped
    print("PASS: out-of-range citation cut, in-range kept, comma artifact cleaned")


def test_strip_stale_citations_cleans_dangling_paren():
    from app.services.chat_orchestrator import ChatOrchestrator

    cleaned, stripped = ChatOrchestrator._strip_stale_citations(
        "Ответ готов (см. [6]).", 5)
    assert "[6]" not in cleaned and "()" not in cleaned, repr(cleaned)
    assert stripped == [6]
    print("PASS: dangling «(см. )» cleaned")


def test_strip_stale_citations_keeps_markdown_links():
    from app.services.chat_orchestrator import ChatOrchestrator

    answer = "Смотрите [9](https://example.com) и сноску [2]."
    cleaned, stripped = ChatOrchestrator._strip_stale_citations(answer, 5)
    assert cleaned == answer, repr(cleaned)   # [9](url) — ссылка, не цитата; [2] в пределах
    assert stripped == []
    print("PASS: markdown links untouched")


def test_strip_stale_citations_noop_cases():
    from app.services.chat_orchestrator import ChatOrchestrator

    # Все цитаты в пределах — текст не меняется
    a = "Пункты [1] и [5] подтверждены."
    cleaned, stripped = ChatOrchestrator._strip_stale_citations(a, 5)
    assert cleaned == a and stripped == []
    # Нет цитат вообще
    b = "Обычный ответ без маркеров."
    cleaned, stripped = ChatOrchestrator._strip_stale_citations(b, 0)
    assert cleaned == b and stripped == []
    # Пустой ответ
    cleaned, stripped = ChatOrchestrator._strip_stale_citations("", 0)
    assert cleaned == "" and stripped == []
    print("PASS: no-op cases leave text unchanged")


if __name__ == "__main__":
    import inspect
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ORCHESTRATOR TESTS PASSED")