"""
Chat endpoint для AI Portfolio.

Единственная публичная точка входа: POST /chat

Pipeline:
HTTP Request → Session Management → Conversation Memory → Response Cache
→ Knowledge Base / RAG → AI Provider Selection → LLM
→ Operational Logging → Conversation Memory → HTTP Response
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db as core_get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.response import ChatResponseDTO
from app.services.cache.response_cache import ResponseCache
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.execution_tracing_service import ExecutionTracingService

router = APIRouter(prefix="/chat", tags=["chat"])


def get_db():
    """Dependency для получения сессии БД."""
    yield from core_get_db()


def get_cache() -> ResponseCache:
    """Dependency для получения кеша."""
    return ResponseCache(
        cache_file="data/cache/response_cache.json",
        ttl_seconds=86400,  # 24 часа
        enable_persistence=True,
    )


def get_orchestrator(
    db: Session = Depends(get_db),
    cache: ResponseCache = Depends(get_cache),
) -> ChatOrchestrator:
    """Dependency для получения ChatOrchestrator."""
    # Lazy import to avoid loading OpenAI API key before dotenv
    from dotenv import load_dotenv
    load_dotenv()

    from app.services.rag.rag_service import RAGService, RAGConfig

    config = RAGConfig(
        collection_name="ai_portfolio_knowledge",
        persist_directory="data/chroma_db",
        embedding_model="text-embedding-3-small",
    )
    rag_service = RAGService(config=config)
    tracing_service = ExecutionTracingService(db=db)

    return ChatOrchestrator(
        db=db,
        cache=cache,
        rag_service=rag_service,
        tracing_service=tracing_service,
    )


def _get_client_ip(request: Request) -> str:
    """Return client IP considering nginx reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    orchestrator: ChatOrchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    """
    Обрабатывает запрос пользователя.

    Pipeline:
    1. Определить сессию
    2. Загрузить память
    3. Проверить Response Cache
    4. При Cache Hit — вернуть ответ
    5. При Cache Miss — выполнить поиск в Knowledge Base
    6. Сформировать контекст
    7. Выбрать активного AI Provider
    8. Выполнить запрос к LLM (с failover)
    9. Сохранить ответ
    10. Записать Execution Trace
    11. Вернуть результат

    Args:
        request: Запрос пользователя
        http_request: HTTP request with client context
        orchestrator: Chat Orchestrator

    Returns:
        ChatResponse с ответом и метаданными
    """
    try:
        # Преобразуем session_id из строки в UUID, если он есть
        session_id = None
        if request.session_id:
            session_id = request.session_id

        # Обрабатываем запрос через orchestrator
        dto: ChatResponseDTO = await orchestrator.process_request(
            user_query=request.message,
            session_id=session_id,
            visitor_id=request.visitor_id,
            client_ip=_get_client_ip(http_request),
            user_agent=http_request.headers.get("user-agent"),
        )

        # Формируем ответ
        return ChatResponse(
            answer=dto.answer,
            session_id=dto.session_id,
            sources=dto.sources,
            provider=dto.provider,
            model=dto.model,
            from_cache=dto.cache_hit,
            rag_used=dto.rag_used,
            response_time_ms=dto.latency_ms,
            user_id=dto.user_id,
            visitor_id=dto.visitor_id,
        )

    except Exception as e:
        # В случае ошибки возвращаем понятное сообщение
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки запроса: {str(e)}",
        )