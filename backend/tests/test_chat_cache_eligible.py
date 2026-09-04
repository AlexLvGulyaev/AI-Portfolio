"""Cache-eligible политика кеша LLM-ответов (04.09.2026).

Возврат кеширования по структурному признаку вместо текстовой эвристики
отказа §3 (0 FP / 3 FN). Версия после расширения решением владельца
04.09.2026: требование цитаты [N] убрано (после перехода на панель
документа большинство прод-ответов цитат не содержит — покрытие было бы
малым). Кешируются grounded-ответы: rag_used, не канонический отказ,
генерация без fallback, без истории. Фикстуры — по образцу
test_chat_orchestrator_fixes._make_orch.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.test_chat_orchestrator_fixes import _make_orch


def _rag_result():
    return SimpleNamespace(
        content="Проект реализует приём заявок.",
        chunk_id="c1",
        score=0.9,
        source="docs/README.md",
        metadata={"repo": "o/Repo-A", "path": "docs/README.md"},
    )


def _rows():
    return [("o/Repo-A", "Проект A", "main", "Проект A")]


def _answer_with_citation():
    return "Проект реализует приём заявок [1]."


def _answer_plain():
    return "Проект реализует приём заявок и выгрузку в CRM.\n\n(Источник: Проект A · README)"


def _run(orch, query):
    return asyncio.run(orch.process_request(user_query=query))


def test_grounded_answer_cached_and_served():
    """Grounded-ответ с цитатой кешируется; повторный тот же вопрос в новой
    сессии — cache-hit без повторной генерации."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    # PromptAssembly замокан классом: фиксируем fingerprint, чтобы ключ кеша
    # был одинаковым у обоих оркестраторов (в бою это строка версии промпта).
    orch.prompt_assembly.fingerprint.return_value = "fp-cache-test"

    gen_calls = {"n": 0}
    provider = MagicMock()

    async def _gen(prompt, **kwargs):
        gen_calls["n"] += 1
        return _answer_with_citation()

    provider.generate.side_effect = _gen
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        d1 = _run(orch, "что умеет Проект A?")
        assert d1.cache_hit is False and d1.rag_used is True
        assert gen_calls["n"] == 1
        assert cache.size() == 1

        # Повтор в новой сессии (memory=[] у нового оркестратора,
        # кеш-инстанс общий — без персистентности он in-memory)
        orch2, rag2, _ = _make_orch(memory=[], cache=cache)
        orch2.prompt_assembly.fingerprint.return_value = "fp-cache-test"
        rag2.search.return_value = [_rag_result()]
        orch2.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
        with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac2:
            Fac2.create.return_value = provider
            d2 = asyncio.run(orch2.process_request(user_query="что умеет Проект A?"))
            assert d2.cache_hit is True
            assert gen_calls["n"] == 1, "повтор не должен вызывать генерацию"
            assert d2.answer == _answer_with_citation()
    print("PASS: grounded answer cached and served on repeat")


def test_plain_answer_without_citation_cached():
    """Ответ без цитат [N] (штатный формат после перехода на панель
    документа) кешируется и отдаётся на повторе — решение владельца
    04.09.2026 о расширении признака."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    orch.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    provider = _fake_provider_answer(_answer_plain())
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        d1 = _run(orch, "как устроена выгрузка в CRM?")
        assert d1.cache_hit is False
    assert cache.size() == 1, "ответ без цитат должен кешироваться"

    orch2, rag2, _ = _make_orch(memory=[], cache=cache)
    orch2.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    rag2.search.return_value = [_rag_result()]
    orch2.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    provider2 = _fake_provider_answer("Заново сгенерированный ответ")
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac2:
        Fac2.create.return_value = provider2
        d2 = asyncio.run(orch2.process_request(user_query="как устроена выгрузка в CRM?"))
        assert d2.cache_hit is True
        assert d2.answer == _answer_plain()
    print("PASS: plain answer (no citations) cached and served")


def test_in_session_repeat_served_from_cache():
    """Дословный повтор вопроса в той же сессии отдаётся из кеша (вариант А,
    решение владельца 04.09.2026): первый задав (без истории) записал ответ,
    повтор с историей — cache-hit без повторной генерации. Регистр и
    пробелы не влияют (нормализация ключа кеша)."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    orch.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    provider = _fake_provider_answer(_answer_with_citation())
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        d1 = _run(orch, "какие шаги демо-маршрута?")
        assert d1.cache_hit is False
    assert cache.size() == 1

    # Повтор в той же сессии: история содержит то же сообщение пользователя
    memory = [SimpleNamespace(role="user", content="Какие шаги демо-маршрута?")]
    orch2, rag2, _ = _make_orch(memory=memory, cache=cache)
    orch2.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    rag2.search.return_value = [_rag_result()]
    orch2.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    provider2 = _fake_provider_answer("Сгенерирован заново — не должен появиться")
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac2:
        Fac2.create.return_value = provider2
        d2 = _run(orch2, "какие шаги ДЕМО-маршрута?")
        assert d2.cache_hit is True
        assert d2.answer == _answer_with_citation()
    print("PASS: in-session identical repeat served from cache")


def test_in_session_new_question_not_served_from_cache():
    """Другой вопрос в той же сессии — контекстно-зависим: генерация,
    чтение кеша не отдаёт чужой ответ."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    orch.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    provider = _fake_provider_answer(_answer_with_citation())
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        _run(orch, "какие шаги демо-маршрута?")
    assert cache.size() == 1

    memory = [SimpleNamespace(role="user", content="какие шаги демо-маршрута?")]
    orch2, rag2, _ = _make_orch(memory=memory, cache=cache)
    orch2.prompt_assembly.fingerprint.return_value = "fp-cache-test"
    rag2.search.return_value = [_rag_result()]
    orch2.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    provider2 = _fake_provider_answer("Ответ на новый вопрос с историей")
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac2:
        Fac2.create.return_value = provider2
        d2 = _run(orch2, "а что проверять на лендинге?")
        assert d2.cache_hit is False
        assert d2.answer == "Ответ на новый вопрос с историей"
    print("PASS: in-session different question generates (no cache)")


def test_is_repeat_query_normalization():
    """Нормализация _is_repeat_query совпадает с ключом кеша: регистр и
    пробелы не влияют; assistant-сообщения и пустой запрос не считаются."""
    from app.services.chat_orchestrator import ChatOrchestrator

    memory = [
        SimpleNamespace(role="user", content="  КАКИЕ   шаги\nдемо-маршрута? "),
        SimpleNamespace(role="assistant", content="какие шаги демо-маршрута?"),
    ]
    assert ChatOrchestrator._is_repeat_query("какие шаги демо-маршрута?", memory) is True
    assert ChatOrchestrator._is_repeat_query("Какие шаги демо-маршрута?", memory) is True
    # assistant-сообщение тем же текстом — не повтор пользователя
    assert ChatOrchestrator._is_repeat_query("какие шаги демо-маршрута?", [
        SimpleNamespace(role="assistant", content="какие шаги демо-маршрута?")]) is False
    assert ChatOrchestrator._is_repeat_query("   ", memory) is False
    assert ChatOrchestrator._is_repeat_query("другой вопрос", memory) is False
    assert ChatOrchestrator._is_repeat_query("другой вопрос", []) is False
    print("PASS: repeat-query normalization matches cache key")


def test_refusal_not_cached():
    """Канонический отказ не кешируется, даже если retrieval что-то нашёл."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    provider = _fake_provider_answer(
        "Прямого кейса про такое в портфолио нет. Такой информации нет в документации."
    )
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        d1 = _run(orch, "экзотический вопрос")
        assert d1.cache_hit is False
    assert cache.size() == 0
    print("PASS: refusal is not cached")


def test_history_answer_not_cached():
    """Ответ на вопрос с историей контекстно-зависим — не пишется в кеш."""
    memory = [SimpleNamespace(role="user", content="привет")]
    orch, rag, cache = _make_orch(memory=memory)
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    provider = _fake_provider_answer(_answer_with_citation())
    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        _run(orch, "уточняющий вопрос")
    assert cache.size() == 0
    print("PASS: history answer is not cached")


def test_fallback_answer_not_cached():
    """Ответ после переключения на fallback-провайдера не кешируется."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()

    primary = MagicMock()
    async def _fail(prompt, **kwargs):
        raise RuntimeError("primary down")
    primary.generate.side_effect = _fail
    fallback = MagicMock()
    async def _ok(prompt, **kwargs):
        return _answer_with_citation()
    fallback.generate.side_effect = _ok

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        # create вызывается синхронно: 1-й вызов — primary, 2-й — fallback
        Fac.create.side_effect = [primary, fallback]
        d1 = _run(orch, "вопрос при падении провайдера")
        assert d1.answer == _answer_with_citation()
    assert cache.size() == 0
    print("PASS: fallback answer is not cached")


def _fake_provider_answer(answer: str):
    provider = MagicMock()
    async def _gen(prompt, **kwargs):
        return answer
    provider.generate.side_effect = _gen
    return provider

def test_refusal_sources_suppressed():
    """Честный отказ отдаётся без источников: retrieval-выдача ничего не
    подтвердила, панель источников под отказом вводит в заблуждение
    (решение владельца 04.09.2026)."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()
    refusal = "В текущем портфеле и базе знаний такой информации нет."

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider_answer(refusal)
        d = _run(orch, "какая завтра погода в Москве?")
    assert "такой информации нет" in d.answer
    assert d.sources == [], "источники при отказе подавляются"
    assert d.metadata.get("sources_detail") in (None, [])
    assert cache.size() == 0


def test_grounded_answer_keeps_sources():
    """Обычный grounded-ответ сохраняет источники — подавление касается
    только канонического отказа."""
    orch, rag, cache = _make_orch(memory=[])
    rag.search.return_value = [_rag_result()]
    orch.db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = _rows()

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = _fake_provider_answer(_answer_plain())
        d = _run(orch, "что умеет Проект A?")
    assert d.sources, "grounded-ответ не должен терять источники"
    assert "Проект A · README" in d.sources[0]


def test_refusal_marker_covers_abbreviation_variant():
    """Вариация отказа «такой аббревиатуры нет» (прод 04.09) тоже
    распознаётся: без кеша и без источников."""
    from app.services.chat_orchestrator import ChatOrchestrator
    assert ChatOrchestrator._is_refusal(
        "В текущем портфеле и базе знаний такой аббревиатуры нет."
    )
    assert not ChatOrchestrator._is_refusal("Проект реализует приём заявок.")
