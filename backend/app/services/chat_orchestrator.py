"""
Chat Orchestrator для AI Portfolio.

Центральный сервис, управляющий жизненным циклом обработки запроса.

Pipeline:
1. Определить сессию
2. Загрузить память
3. Проверить Response Cache
4. При Cache Hit — вернуть ответ
5. При Cache Miss — выполнить поиск в Knowledge Base
6. Сформировать контекст
7. Выбрать активного AI Provider
8. Выполнить запрос к LLM
9. Сохранить ответ
10. Записать Operational Log
11. Вернуть результат

Источники:
- Assistant Flow: pipeline обработки запроса
- Review Flow: интеграция сервисов
- PEcf09: RAG integration
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.response import ChatResponseDTO
from app.services.ai_provider_settings_service import AIProviderSettingsService
from app.services.cache.response_cache import ResponseCache
from app.services.chat_session_service import ChatSessionService
from app.services.conversation_memory_service import ConversationMemoryService
from app.services.operational_log_service import OperationalLogService
from app.services.prompt_assembly import PromptAssembly
from app.services.providers.base import AIProvider
from app.services.providers.factory import AIProviderFactory
from app.services.rag.rag_service import RAGService


class ChatOrchestrator:
    """
    Центральный сервис, управляющий жизненным циклом обработки запроса.

    Именно ChatOrchestrator определяет последовательность вызова остальных сервисов.
    Orchestration не переносится внутрь контроллеров FastAPI.
    """

    def __init__(
        self,
        *,
        db: Session,
        cache: ResponseCache,
        rag_service: RAGService,
        cache_ttl_seconds: int = 86400,  # 24 часа
        rag_top_k: int = 3,
    ):
        """
        Инициализация ChatOrchestrator.

        Args:
            db: Сессия базы данных
            cache: Сервис кеширования
            rag_service: Сервис RAG
            cache_ttl_seconds: Время жизни кеша
            rag_top_k: Количество документов для RAG
        """
        self.db = db
        self.cache = cache
        self.rag_service = rag_service
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rag_top_k = rag_top_k

        # Инициализируем сервисы
        self.session_service = ChatSessionService(db)
        self.memory_service = ConversationMemoryService(db=db)
        self.provider_settings = AIProviderSettingsService(db)
        self.log_service = OperationalLogService(db)
        self.prompt_assembly = PromptAssembly()

    async def process_request(
        self,
        user_query: str,
        session_id: uuid.UUID | None = None,
        visitor_id: uuid.UUID | None = None,
    ) -> ChatResponseDTO:
        """
        Обрабатывает запрос пользователя.

        Полный pipeline:
        1. Определить сессию
        2. Загрузить память
        3. Проверить Response Cache
        4. При Cache Hit — вернуть ответ
        5. При Cache Miss — выполнить поиск в Knowledge Base
        6. Сформировать контекст
        7. Выбрать активного AI Provider
        8. Выполнить запрос к LLM (с failover)
        9. Сохранить ответ
        10. Записать Operational Log
        11. Вернуть результат

        Args:
            user_query: Запрос пользователя
            session_id: ID сессии (если None, создаётся новая)
            visitor_id: ID посетителя (если None, создаётся новый)

        Returns:
            ChatResponseDTO с ответом и метаданными
        """
        start_time = time.monotonic()

        # 1. Определить сессию
        if not visitor_id:
            visitor_id = uuid.uuid4()

        if not session_id:
            session_id = self.session_service.create_session(
                visitor_id=str(visitor_id), mode="text"
            )
        else:
            # Validate that the provided session_id actually exists.
            # If a client sends a stale/deleted session_id, create a new one
            # instead of failing with a ForeignKeyViolation later.
            existing = self.session_service.get_session_by_id(session_id)
            if not existing:
                session_id = self.session_service.create_session(
                    visitor_id=str(visitor_id), mode="text"
                )

        # 2. Загрузить память
        conversation_memory = self.memory_service.get_recent_messages(
            str(session_id), limit=10
        )

        # 3. Проверить Response Cache
        cached_response = self.cache.get(user_query)
        if cached_response:
            # Cache Hit
            response_time_ms = int((time.monotonic() - start_time) * 1000)

            # Записать сообщение в память
            self.memory_service.add_message(
                session_id=str(session_id),
                user_id=str(visitor_id),
                role="user",
                content=user_query,
            )
            self.memory_service.add_message(
                session_id=str(session_id),
                user_id=str(visitor_id),
                role="assistant",
                content=cached_response,
                metadata={"from_cache": True},
            )

            # Получить метаданные из кеша
            cache_entry = self.cache.get_entry(user_query)
            provider = cache_entry.metadata.get("provider", "unknown") if cache_entry else "unknown"
            model = cache_entry.metadata.get("model", "unknown") if cache_entry else "unknown"
            sources = cache_entry.metadata.get("sources", []) if cache_entry else []

            return ChatResponseDTO(
                answer=cached_response,
                session_id=session_id,
                user_id=visitor_id,
                provider=provider,
                model=model,
                cache_hit=True,
                rag_used=False,
                sources=sources,
                latency_ms=response_time_ms,
                metadata={"from_cache": True},
            )

        # 4. Поиск в Knowledge Base (RAG)
        rag_context = ""
        rag_results = []
        rag_used = False
        sources: list[str] = []

        if self.rag_service.count_documents() > 0:
            rag_results = self.rag_service.search(user_query, top_k=self.rag_top_k)
            if rag_results:
                rag_context = self.rag_service.get_context(user_query, top_k=self.rag_top_k)
                rag_used = True
                sources = [r.source for r in rag_results]

        # 5. Сформировать prompt
        prompt = self.prompt_assembly.build(
            user_query=user_query,
            conversation_memory=conversation_memory,
            rag_context=rag_context if rag_context else None,
        )

        # 6. Выбрать активного AI Provider
        active_row, warnings = self.provider_settings.get_effective_provider()

        # Если нет активного провайдера, использовать fallback
        if not active_row:
            fallback_row = self.provider_settings.get_fallback()
            if fallback_row:
                active_row = fallback_row
                # Логируем переключение
                self.log_service.log_provider_switch(
                    provider_key=fallback_row.provider_key,
                    model_name=fallback_row.model_name or "unknown",
                    status="ok",
                    metadata={"reason": "No active provider, using fallback"},
                )
            else:
                # Нет ни активного, ни fallback провайдера
                error_message = "No AI provider available"
                response_time_ms = int((time.monotonic() - start_time) * 1000)

                return ChatResponseDTO(
                    answer="Извините, система временно недоступна. Попробуйте позже.",
                    session_id=session_id,
                    user_id=visitor_id,
                    provider="none",
                    model="none",
                    cache_hit=False,
                    rag_used=False,
                    sources=[],
                    latency_ms=response_time_ms,
                    metadata={"error": error_message},
                )

        active_config = self.provider_settings.build_effective_config(active_row)
        provider_key = active_config.provider_key
        model_name = active_config.model_name or "unknown"

        # 7. Выполнить запрос к LLM (с failover)
        answer = None
        provider_used = provider_key
        model_used = model_name
        fallback_used = False
        error_message = None

        try:
            # Пытаемся использовать основной провайдер
            provider = AIProviderFactory.create(provider_key, config=active_config)
            answer = await provider.generate(
                prompt,
                temperature=active_config.temperature,
                max_tokens=active_config.max_tokens,
            )

        except Exception as e:
            # Failover: переключаемся на fallback провайдер
            error_message = str(e)

            fallback_row = self.provider_settings.get_fallback()
            if fallback_row:
                fallback_config = self.provider_settings.build_effective_config(fallback_row)
                fallback_used = True
                provider_used = fallback_config.provider_key
                model_used = fallback_config.model_name or "unknown"

                try:
                    provider = AIProviderFactory.create(
                        fallback_config.provider_key, config=fallback_config
                    )
                    answer = await provider.generate(
                        prompt,
                        temperature=fallback_config.temperature,
                        max_tokens=fallback_config.max_tokens,
                    )

                    # Логируем переключение провайдера
                    self.log_service.log_provider_switch(
                        provider_key=fallback_config.provider_key,
                        model_name=fallback_config.model_name or "unknown",
                        status="ok",
                        metadata={"reason": f"Primary provider failed: {error_message}"},
                    )

                except Exception as fallback_error:
                    # Fallback тоже не сработал
                    error_message = f"Both primary and fallback providers failed. Primary: {error_message}. Fallback: {fallback_error}"
                    answer = self._get_error_response(error_message)

        # 8. Сохранить в кеш
        self.cache.set(
            query=user_query,
            response=answer,
            metadata={
                "provider": provider_used,
                "model": model_used,
                "sources": sources,
                "session_id": str(session_id),
            },
            ttl_seconds=self.cache_ttl_seconds,
        )

        # 9. Сохранить в память
        self.memory_service.add_message(
            session_id=str(session_id),
            user_id=str(visitor_id),
            role="user",
            content=user_query,
        )
        self.memory_service.add_message(
            session_id=str(session_id),
            user_id=str(visitor_id),
            role="assistant",
            content=answer,
            metadata={
                "provider": provider_used,
                "model": model_used,
                "rag_used": rag_used,
                "sources": sources,
            },
        )

        # 10. Записать Operational Log
        response_time_ms = int((time.monotonic() - start_time) * 1000)

        self.log_service.log_chat_request(
            session_id=str(session_id),
            user_id=str(visitor_id),
            query=user_query,
            response=answer,
            model_name=model_used,
            provider_key=provider_used,
            from_cache=False,
            response_time_ms=response_time_ms,
            status="ok" if not error_message else "error",
            metadata={
                "rag_used": rag_used,
                "sources": sources,
                "fallback_used": fallback_used,
                "error": error_message,
            },
        )

        # 11. Вернуть результат
        return ChatResponseDTO(
            answer=answer,
            session_id=session_id,
            user_id=visitor_id,
            provider=provider_used,
            model=model_used,
            cache_hit=False,
            rag_used=rag_used,
            sources=sources,
            latency_ms=response_time_ms,
            metadata={
                "fallback_used": fallback_used,
                "error": error_message,
            },
        )

    def _get_error_response(self, error_message: str) -> str:
        """
        Формирует ответ при ошибке.

        Args:
            error_message: Сообщение об ошибке

        Returns:
            Ответ для пользователя
        """
        return f"Извините, произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."

    def get_session_history(
        self,
        session_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Any]:
        """
        Возвращает историю сессии.

        Args:
            session_id: ID сессии
            limit: Максимальное количество сообщений

        Returns:
            Список сообщений
        """
        return self.memory_service.get_recent_messages(str(session_id), limit=limit)