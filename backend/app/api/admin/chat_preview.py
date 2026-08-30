"""
Admin chat-preview — канал проверки KB владельцем (§5.1 п. 9, решение
владельца 29.08.2026, вариант «В1»).

Пайплайн владельца: «загрузили документы в KB → проверили работу
ассистента → если блокеров нет, загрузили на лендинг». Публичный ассистент
на шаге проверки ещё не отдаёт документы скрытой карточки (retrieval guard,
В1) — поэтому владельцу нужен собственный канал: тот же ChatOrchestrator,
но с include_hidden=True — retrieval guard снят, и владелец видит ровно
то, как ассистент ответил бы по документам ещё неопубликованного проекта.

Скрытый проект не резолвится и в prompt-реестре (он строится из видимых
карточек) — это сознательно: владелец проверяет KB-ответы по документам
(«что ассистент вытащит из репозитория»), а не витринную карточку.

Trace-каналы помечены visitor_id="admin-preview", чтобы пробы владельца
были отличимы от публичного трафика в execution sessions / логах.
Кеш — отдельный файл: канал владельца не читает и не пишет публичный кеш.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db as core_get_db

router = APIRouter()


class ChatPreviewRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None


class ChatPreviewResponse(BaseModel):
    answer: str
    session_id: uuid.UUID | None = None
    sources: list = []
    sources_detail: list | None = None
    provider: str | None = None
    model: str | None = None
    rag_used: bool = False
    response_time_ms: int = 0


def _get_client_ip(request: Request) -> str:
    """Return client IP considering nginx reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


@router.post("/chat-preview", response_model=ChatPreviewResponse)
async def chat_preview(
    body: ChatPreviewRequest,
    http_request: Request,
    db: Session = Depends(core_get_db),
    _: None = Depends(require_admin),
) -> ChatPreviewResponse:
    """
    Запуск оркестратора в канале владельца: как в публичном чате, но без
    retrieval-гварда скрытых проектов. Для проверки KB-ответов по проекту,
    который ещё не опубликован («Скрыт»).
    """
    try:
        # Lazy imports: тот же порядок инициализации, что у публичного /chat.
        from dotenv import load_dotenv

        load_dotenv()

        from app.services.cache.response_cache import ResponseCache
        from app.services.chat_orchestrator import ChatOrchestrator
        from app.services.execution_tracing_service import ExecutionTracingService
        from app.services.rag.retrieval_manager import get_retrieval_manager

        cache = ResponseCache(
            cache_file="data/cache/admin_preview_cache.json",
            ttl_seconds=86400,
            enable_persistence=True,
        )
        rag_service = get_retrieval_manager().get_backend()
        orchestrator = ChatOrchestrator(
            db=db,
            cache=cache,
            rag_service=rag_service,
            tracing_service=ExecutionTracingService(db=db),
            include_hidden=True,
        )

        dto = await orchestrator.process_request(
            user_query=body.message,
            session_id=body.session_id,
            visitor_id="admin-preview",
            client_ip=_get_client_ip(http_request),
            user_agent=f"admin-preview; {http_request.headers.get('user-agent', '')}",
        )
        return ChatPreviewResponse(
            answer=dto.answer,
            session_id=dto.session_id,
            sources=dto.sources,
            sources_detail=dto.metadata.get("sources_detail"),
            provider=dto.provider,
            model=dto.model,
            rag_used=dto.rag_used,
            response_time_ms=dto.latency_ms,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки запроса чата: {str(e)}",
        )