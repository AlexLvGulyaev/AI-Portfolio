"""
Unit-тесты стриминга (10.09.2026, вариант A: SSE + TTFT).

Покрывают:
- _StreamHygieneFilter: потоковый аналог пост-гигиены (устаревшие
  цитаты [N>кол-во источников], метки оград ```python, разрыв маркеров
  между дельтами);
- оркестратор: on_token-маршрут (generate_stream → коллбэк → сборка
  ответа), ttft_ms в метаданных;
- детерминированные маршруты не вызывают on_token;
- политика переключения «только до первого токена»: обрыв до первой
  дельты → фолбэк-провайдер; обрыв после → StreamingGenerationError
  (тихой подмены нет);
- SSE-эндпойнт /chat/stream: delta/final/[DONE], заголовки text/event-stream.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.chat_orchestrator import (  # noqa: E402
    StreamingGenerationError,
    _StreamHygieneFilter,
)
from tests.test_chat_orchestrator_fixes import _make_orch  # noqa: E402


# ---------- _StreamHygieneFilter ----------

def test_filter_passes_plain_text():
    f = _StreamHygieneFilter(3)
    out = f.feed("Привет! ") + f.feed("Как дела?") + f.flush()
    assert out == "Привет! Как дела?"


def test_filter_drops_stale_citation():
    f = _StreamHygieneFilter(2)
    out = f.feed("Ответ [7] готов.") + f.flush()
    assert out == "Ответ  готов."


def test_filter_keeps_valid_citation():
    f = _StreamHygieneFilter(3)
    out = f.feed("Ответ [2] готов.") + f.flush()
    assert out == "Ответ [2] готов."


def test_filter_citation_split_across_deltas():
    f = _StreamHygieneFilter(5)
    out = f.feed("Ответ [") + f.feed("1] и ещё") + f.flush()
    assert out == "Ответ [1] и ещё"


def test_filter_stale_citation_split_across_deltas_dropped():
    f = _StreamHygieneFilter(1)
    out = f.feed("Ответ [") + f.feed("9] конец") + f.flush()
    assert out == "Ответ  конец"


def test_filter_fence_label_python_stripped():
    f = _StreamHygieneFilter(2)
    out = f.feed("```python\nx = 1") + f.flush()
    assert out == "```\nx = 1"


def test_filter_fence_label_markdown_kept():
    f = _StreamHygieneFilter(2)
    out = f.feed("```markdown\n## Заголовок") + f.flush()
    assert out == "```markdown\n## Заголовок"


def test_filter_bare_fence_kept():
    f = _StreamHygieneFilter(2)
    out = f.feed("```\ncode") + f.flush()
    assert out == "```\ncode"


def test_filter_bare_backticks_not_fence():
    f = _StreamHygieneFilter(2)
    out = f.feed("код в ``x``") + f.flush()
    assert out == "код в ``x``"


def test_filter_flush_emits_held_tail():
    f = _StreamHygieneFilter(3)
    out = f.feed("текст [1") + f.flush()
    assert out == "текст [1"


# ---------- _StreamHygieneFilter: markdown-разметка (замечание приёмки 04.09) ----------

def test_filter_bold_pair_cut_in_one_delta():
    f = _StreamHygieneFilter(3)
    out = f.feed("**Backend:** готов к работе.") + f.flush()
    assert out == "Backend: готов к работе."


def test_filter_bold_pair_split_across_deltas():
    f = _StreamHygieneFilter(3)
    out = f.feed("**Lead Qualification") + f.feed("**: отбор заявок.") + f.flush()
    assert out == "Lead Qualification: отбор заявок."


def test_filter_single_star_pair_split_across_deltas():
    # пара «*текст*» разрезана между дельтами
    f = _StreamHygieneFilter(3)
    out = f.feed("*Маршрут") + f.feed(" проверки* демо") + f.flush()
    assert out == "Маршрут проверки демо"


def test_filter_single_star_unpaired_stays_literal():
    f = _StreamHygieneFilter(3)
    out = f.feed("**незакрытый жирный\nдальше текст") + f.flush()
    assert out == "**незакрытый жирный\nдальше текст"


def test_filter_multiplication_stars_preserved():
    f = _StreamHygieneFilter(3)
    out = f.feed("прирост 2*3=6 единиц") + f.flush()
    assert out == "прирост 2*3=6 единиц"


def test_filter_star_bullet_to_dash():
    f = _StreamHygieneFilter(3)
    out = f.feed("Список:\n* первый пункт\n* второй") + f.flush()
    assert out == "Список:\n- первый пункт\n- второй"


def test_filter_heading_cut_to_text():
    f = _StreamHygieneFilter(3)
    out = f.feed("# Маршрут проверки\nШаг 1.") + f.flush()
    assert out == "Маршрут проверки\nШаг 1."


def test_filter_heading_split_across_deltas():
    f = _StreamHygieneFilter(3)
    out = f.feed("## Требования") + f.feed(" к демо\n") + f.flush()
    assert out == "Требования к демо\n"


def test_filter_inline_hash_is_literal():
    f = _StreamHygieneFilter(3)
    out = f.feed("язык C# и хештеги") + f.flush()
    assert out == "язык C# и хештеги"


# ---------- пост-гигиена: _strip_markdown_emphasis ----------

def test_posthygiene_bold_and_heading():
    orch, _, _ = _make_orch(None)
    ans = "**Lead Qualification**: отбор заявок.\n# Маршрут проверки\nШаг 1."
    assert orch._strip_markdown_emphasis(ans) == "Lead Qualification: отбор заявок.\nМаршрут проверки\nШаг 1."


def test_posthygiene_unpaired_bold_removed():
    orch, _, _ = _make_orch(None)
    assert orch._strip_markdown_emphasis("начало **оборванный текст") == "начало оборванный текст"


def test_posthygiene_multiplication_preserved():
    orch, _, _ = _make_orch(None)
    assert orch._strip_markdown_emphasis("2*3=6 и 3*4*5=60 и 2 * 3") == "2*3=6 и 3*4*5=60 и 2 * 3"


def test_posthygiene_single_emphasis_cut():
    orch, _, _ = _make_orch(None)
    assert orch._strip_markdown_emphasis("это *важно* для демо") == "это важно для демо"


def test_posthygiene_star_bullet_to_dash():
    orch, _, _ = _make_orch(None)
    assert orch._strip_markdown_emphasis("* пункт один\n* пункт два") == "- пункт один\n- пункт два"


def test_posthygiene_plain_text_untouched():
    orch, _, _ = _make_orch(None)
    assert orch._strip_markdown_emphasis("Обычный ответ без разметки.") == "Обычный ответ без разметки."


# ---------- оркестратор: on_token-маршрут ----------

def _stream_provider(chunks, *, fail_after=None):
    provider = MagicMock()

    async def _gen_stream(prompt, **kwargs):
        for i, chunk in enumerate(chunks):
            if fail_after is not None and i >= fail_after:
                raise RuntimeError("stream broke")
            yield chunk

    provider.generate_stream.side_effect = _gen_stream
    return provider


def test_orchestrator_stream_collects_deltas_and_ttft():
    orch, _, _ = _make_orch(memory=[])
    provider = _stream_provider(["Первая ", "вторая ", "третья"])
    collected = []

    async def _on_token(piece):
        collected.append(piece)

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.return_value = provider
        dto = asyncio.run(orch.process_request(
            user_query="Что это за платформа?", on_token=_on_token,
        ))

    assert dto.answer == "Первая вторая третья"
    assert collected == ["Первая ", "вторая ", "третья"]
    assert dto.metadata.get("streamed") is True
    assert dto.metadata.get("ttft_ms") is not None
    print("PASS: on_token stream path assembles answer and records ttft_ms")


def test_deterministic_route_never_calls_on_token():
    orch, _, _ = _make_orch(memory=[], registry={
        "classify": lambda q: "listing",
        "render_list": lambda: "В портфолио 13 проектов:\n1. X",
    })
    collected = []

    async def _on_token(piece):
        collected.append(piece)

    with patch("app.services.chat_orchestrator.AIProviderFactory"):
        dto = asyncio.run(orch.process_request(
            user_query="Какие проекты есть в портфолио?", on_token=_on_token,
        ))

    assert dto.answer.startswith("В портфолио 13 проектов")
    assert collected == []
    # Детерминированный маршрут возвращается до стрим-логики: metadata
    # без ttft/streamed — SSE-маршрут отдаст ответ одиночной дельтой
    assert dto.metadata.get("streamed") is None
    print("PASS: deterministic route emits no deltas")


def test_stream_failure_before_first_token_falls_back():
    orch, _, _ = _make_orch(memory=[])
    primary = _stream_provider(["никогда"], fail_after=0)
    fallback = _stream_provider(["Фолбэк "])
    fallback_row = MagicMock()
    primary_cfg = SimpleNamespace(
        provider_key="openai", model_name="m1", temperature=0.2, max_tokens=500,
    )
    fallback_cfg = SimpleNamespace(
        provider_key="gigachat", model_name="m2", temperature=0.2, max_tokens=500,
    )
    orch.provider_settings.get_fallback.return_value = fallback_row
    orch.provider_settings.build_effective_config.side_effect = (
        lambda row: fallback_cfg if row is fallback_row else primary_cfg
    )
    collected = []

    async def _on_token(piece):
        collected.append(piece)

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.side_effect = (
            lambda key, config: fallback if config is fallback_cfg else primary
        )
        dto = asyncio.run(orch.process_request(
            user_query="Что это за платформа?", on_token=_on_token,
        ))

    # Обрыв до первого токена: фолбэк стартует стрим заново — его дельты
    # честно доходят зрителю (переключение произошло до первого токена)
    assert collected == ["Фолбэк "]
    assert dto.answer == "Фолбэк "
    assert dto.metadata.get("streamed") is True
    print("PASS: failure before first token switches to fallback silently")


def test_stream_failure_after_first_token_raises():
    orch, _, _ = _make_orch(memory=[])
    # Второй чанк обязан существовать: генератор рвётся в начале
    # следующей итерации (поток оборвался «на середине»)
    provider = _stream_provider(["Частичный ", "ещё"], fail_after=1)
    fallback_row = MagicMock()
    primary_cfg = SimpleNamespace(
        provider_key="openai", model_name="m1", temperature=0.2, max_tokens=500,
    )
    fallback_cfg = SimpleNamespace(
        provider_key="gigachat", model_name="m2", temperature=0.2, max_tokens=500,
    )
    orch.provider_settings.get_fallback.return_value = fallback_row
    orch.provider_settings.build_effective_config.side_effect = (
        lambda row: fallback_cfg if row is fallback_row else primary_cfg
    )
    collected = []

    async def _on_token(piece):
        collected.append(piece)

    with patch("app.services.chat_orchestrator.AIProviderFactory") as Fac:
        Fac.create.side_effect = (
            lambda key, config: _stream_provider(["запасной"]) if config is fallback_cfg else provider
        )
        try:
            asyncio.run(orch.process_request(
                user_query="Что это за платформа?", on_token=_on_token,
            ))
        except StreamingGenerationError:
            pass
        else:
            raise AssertionError(
                "Ожидался StreamingGenerationError: тихая подмена после начала потока запрещена"
            )

    # Частичный текст был отдан зрителю ДО обрыва
    assert collected == ["Частичный "]
    print("PASS: mid-stream failure raises honestly, no silent substitution")


# ---------- SSE-эндпойнт ----------

def _sse_parse(chunks):
    events = []
    for chunk in chunks:
        for raw in chunk.split("\n\n"):
            raw = raw.strip()
            if not raw:
                continue
            assert raw.startswith("data: ")
            body = raw[len("data: "):]
            events.append(body)
    return events


def test_chat_stream_endpoint_delta_final_done():
    from app.api.chat_stream import chat_stream
    from app.schemas.chat import ChatRequest

    collected = []

    async def _on_token(piece):
        collected.append(piece)

    async def _process(**kwargs):
        assert kwargs["on_token"] is not None
        await kwargs["on_token"]("Стрим-")
        await kwargs["on_token"]("ответ")
        return SimpleNamespace(
            answer="Стрим-ответ", session_id=uuid.uuid4(), sources=["X"],
            metadata={"sources_detail": [], "ttft_ms": 120},
            provider="openai", model="m1", cache_hit=False, rag_used=True,
            latency_ms=800, user_id=uuid.uuid4(), visitor_id=None,
        )

    orch = MagicMock()
    orch.process_request.side_effect = _process

    http_request = MagicMock()
    http_request.headers = {"user-agent": "pytest"}

    request = ChatRequest(message="тест")
    response = asyncio.run(chat_stream(request, http_request, orchestrator=orch))

    assert response.media_type == "text/event-stream"
    assert response.headers.get("cache-control") == "no-cache"
    assert response.headers.get("x-accel-buffering") == "no"

    chunks = asyncio.run(_collect(response.body_iterator))
    events = _sse_parse(chunks)
    assert events[-1] == "[DONE]"
    parsed = [__import__("json").loads(e) for e in events if e != "[DONE]"]
    types = [p["type"] for p in parsed]
    assert types == ["start", "delta", "delta", "final"]
    assert parsed[1]["text"] == "Стрим-"
    assert parsed[2]["text"] == "ответ"
    final = parsed[3]
    assert final["answer"] == "Стрим-ответ"
    assert final["ttft_ms"] == 120
    assert final["sources"] == ["X"]
    assert final["provider"] == "openai"
    print("PASS: SSE endpoint emits start/delta/final/[DONE] with headers")


def test_chat_stream_endpoint_cache_hit_single_delta():
    from app.api.chat_stream import chat_stream
    from app.schemas.chat import ChatRequest

    async def _process(**kwargs):
        assert kwargs["on_token"] is not None
        return SimpleNamespace(
            answer="Из кеша", session_id=uuid.uuid4(), sources=[],
            metadata={"sources_detail": [], "ttft_ms": None},
            provider="cache", model="fingerprint", cache_hit=True, rag_used=False,
            latency_ms=15, user_id=uuid.uuid4(), visitor_id=None,
        )

    orch = MagicMock()
    orch.process_request.side_effect = _process

    http_request = MagicMock()
    http_request.headers = {}

    request = ChatRequest(message="тест")
    response = asyncio.run(chat_stream(request, http_request, orchestrator=orch))
    chunks = asyncio.run(_collect(response.body_iterator))
    events = _sse_parse(chunks)
    assert events[-1] == "[DONE]"
    parsed = [__import__("json").loads(e) for e in events if e != "[DONE]"]
    types = [p["type"] for p in parsed]
    # Кеш-hit: оркестратор не вызывает on_token → маршрут отдаёт полный
    # ответ одним delta-событием
    assert types == ["start", "delta", "final"]
    assert parsed[1]["text"] == "Из кеша"
    assert parsed[2]["from_cache"] is True
    print("PASS: cache-hit answer delivered as single delta")


async def _collect(iterator):
    out = []
    async for chunk in iterator:
        chunks = chunk if isinstance(chunk, (list, tuple)) else [chunk]
        for c in chunks:
            if isinstance(c, bytes):
                c = c.decode("utf-8")
            chunks_out = c if isinstance(c, (list, tuple)) else [c]
            for piece in chunks_out:
                if isinstance(piece, bytes):
                    piece = piece.decode("utf-8")
                if isinstance(piece, str):
                    out.append(piece)
                else:
                    # Starlette отдаёт сообщения как str/bytes-обёртки
                    out.append(str(getattr(piece, "data", piece)))
    return out


if __name__ == "__main__":
    import inspect

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
    print("ALL STREAMING TESTS PASSED")