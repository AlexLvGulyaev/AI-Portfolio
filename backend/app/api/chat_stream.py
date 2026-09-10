"""SSE-эндпойнт стрим-чата AI Portfolio.

POST /chat/stream — потоковая выдача ответа (10.09.2026, вариант A
послеприёмочного плана): зритель читает ответ по мере генерации.

Формат событий (SSE, text/event-stream), data: <JSON>:
- {"type": "delta", "text": "..."}       — гигиеничная дельта текста
- {"type": "final", ...ChatResponse}     — метаданные после генерации
  (sources в финальном событии: семантика подавления источников при
  отказе, решение владельца 04.09, сохраняется дословно)
- {"type": "error", "message": "..."}    — честный обрыв (после начала
  потока тихой подмены нет; переключение провайдера — только до первого
  токена)
Завершение: data: [DONE]

JSON-контракт POST /chat не меняется (админка, eval, case-match).
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.chat import _get_client_ip, get_orchestrator
from app.schemas.chat import ChatRequest
from app.schemas.response import ChatResponseDTO
from app.services.admin.system_prompt_service import PromptUnavailableError
from app.services.chat_orchestrator import StreamingGenerationError

router = APIRouter(prefix="/chat/stream", tags=["chat"])
logger = logging.getLogger(__name__)

_SSE_DONE = "data: [DONE]\n\n"


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    orchestrator: Any = Depends(get_orchestrator),
) -> StreamingResponse:
    """Потоковый чат: дельты по мере генерации, метаданные в финальном
    событии. Fingerprint-кеш и детерминированные маршруты отдают полный
    ответ одним delta-событием (без TTFT-выигрыша — ответ готов до
    генерации)."""

    async def event_stream() -> AsyncIterator[str]:
        yield _sse({"type": "start"})
        queue: asyncio.Queue = asyncio.Queue()

        async def on_token(piece: str) -> None:
            await queue.put({"type": "delta", "text": piece})

        _SENTINEL = object()

        def _task_done(_task: "asyncio.Task") -> None:
            queue.put_nowait(_SENTINEL)

        task = asyncio.create_task(
            orchestrator.process_request(
                user_query=request.message,
                session_id=request.session_id,
                visitor_id=request.visitor_id,
                page_slug=request.page_slug,
                client_ip=_get_client_ip(http_request),
                user_agent=http_request.headers.get("user-agent"),
                on_token=on_token,
            )
        )
        task.add_done_callback(_task_done)

        deltas_emitted = 0
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            deltas_emitted += 1
            yield _sse(item)

        try:
            dto = await task
        except PromptUnavailableError:
            # Решение B (09.09.2026): нет активного промпта — честная
            # деградация; стрим уже открыт (200), ошибка — событием.
            yield _sse({"type": "error", "message": "Ассистент временно недоступен. Попробуйте позже."})
            yield _SSE_DONE
            return
        except StreamingGenerationError:
            yield _sse({"type": "error", "message": "Генерация ответа прервана. Попробуйте ещё раз."})
            yield _SSE_DONE
            return
        except Exception:
            logger.exception("chat stream request failed")
            yield _sse({"type": "error", "message": "Не удалось обработать запрос. Попробуйте позже."})
            yield _SSE_DONE
            return

        try:
            if deltas_emitted == 0:
                # Cache-hit / детерминированный маршрут: ответ готов до
                # генерации — отдаём одним событием.
                yield _sse({"type": "delta", "text": dto.answer})
            yield _sse({
                "type": "final",
                "answer": dto.answer,
                "session_id": str(dto.session_id),
                "sources": dto.sources,
                "sources_detail": dto.metadata.get("sources_detail"),
                "provider": dto.provider,
                "model": dto.model,
                "from_cache": dto.cache_hit,
                "rag_used": dto.rag_used,
                "response_time_ms": dto.latency_ms,
                "ttft_ms": dto.metadata.get("ttft_ms"),
                "user_id": str(dto.user_id) if dto.user_id else None,
                "visitor_id": str(dto.visitor_id) if dto.visitor_id else None,
            })
            yield _SSE_DONE
        except Exception:
            logger.exception("chat stream: final event serialization failed")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx: отключить буферизацию проксированного ответа для
            # этого ответа (SSE), без глобального proxy_buffering off
            "X-Accel-Buffering": "no",
        },
    )