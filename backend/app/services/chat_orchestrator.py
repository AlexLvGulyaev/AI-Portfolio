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
from app.services.execution_tracing_service import ExecutionTracingService
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
        tracing_service: ExecutionTracingService | None = None,
        cache_ttl_seconds: int = 86400,  # 24 часа
        rag_top_k: int = 3,
    ):
        """
        Инициализация ChatOrchestrator.

        Args:
            db: Сессия базы данных
            cache: Сервис кеширования
            rag_service: Сервис RAG
            tracing_service: Опциональный сервис execution tracing
            cache_ttl_seconds: Время жизни кеша
            rag_top_k: Количество документов для RAG
        """
        self.db = db
        self.cache = cache
        self.rag_service = rag_service
        self.tracing_service = tracing_service
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rag_top_k = rag_top_k

        # Инициализируем сервисы
        self.session_service = ChatSessionService(db)
        self.memory_service = ConversationMemoryService(db=db)
        self.provider_settings = AIProviderSettingsService(db)
        self.prompt_assembly = PromptAssembly()

    async def process_request(
        self,
        user_query: str,
        session_id: uuid.UUID | None = None,
        visitor_id: uuid.UUID | str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
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
        10. Записать Execution Trace
        11. Вернуть результат

        Args:
            user_query: Запрос пользователя
            session_id: ID сессии (если None, создаётся новая)
            visitor_id: ID посетителя (если None, создаётся новый)
            client_ip: IP-адрес клиента
            user_agent: User-Agent клиента

        Returns:
            ChatResponseDTO с ответом и метаданными
        """
        start_time = time.monotonic()
        execution_id: uuid.UUID | None = None
        step_ids: dict[str, uuid.UUID] = {}

        def _start_step(stage_name: str, step_order: int, metadata: dict[str, Any] | None = None) -> None:
            if self.tracing_service and execution_id:
                step_ids[stage_name] = self.tracing_service.start_step(
                    execution_id, stage_name, step_order, metadata
                )

        def _finish_step(stage_name: str, status: str = "ok", metadata: dict[str, Any] | None = None) -> None:
            if self.tracing_service and stage_name in step_ids:
                self.tracing_service.finish_step(step_ids[stage_name], status, metadata)

        def _skip_step(stage_name: str, step_order: int, metadata: dict[str, Any] | None = None) -> None:
            if self.tracing_service and execution_id:
                self.tracing_service.skip_step(execution_id, stage_name, step_order, metadata)

        def _finalize(status: str, metadata: dict[str, Any] | None = None) -> None:
            if self.tracing_service and execution_id:
                try:
                    self.tracing_service.finish_session(execution_id, status, metadata)
                except Exception:
                    # Tracing must not break the main response path.
                    pass

        try:
            # 1. Определить сессию
            if not visitor_id:
                visitor_id = uuid.uuid4()
            elif isinstance(visitor_id, str):
                try:
                    visitor_id = uuid.UUID(visitor_id)
                except ValueError:
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

            # Start execution tracing once the real session_id is known.
            if self.tracing_service:
                execution_id = self.tracing_service.start_session(
                    session_id=session_id,
                    user_id=visitor_id,
                    visitor_id=visitor_id,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    event_type="chat_request",
                    route="text",
                    metadata={"query": user_query},
                )

            _start_step("session_resolve", 1, {"query": user_query, "session_id": str(session_id)})
            _finish_step("session_resolve", "ok", {"query": user_query, "session_id": str(session_id)})

            # 2. Загрузить память
            _start_step("memory_load", 2)
            conversation_memory = self.memory_service.get_recent_messages(
                str(session_id), limit=10
            )
            _finish_step("memory_load", "ok", {
                "message_count": len(conversation_memory),
                "session_id": str(session_id),
            })

            # 3. Проверить Response Cache
            _start_step("cache_check", 3)
            cached_response = self.cache.get(user_query)
            if cached_response:
                _finish_step("cache_check", "ok", {
                    "cache_hit": True,
                    "query": user_query,
                    "provider": provider,
                    "model": model,
                })

                # Получить метаданные из кеша
                cache_entry = self.cache.get_entry(user_query)
                provider = cache_entry.metadata.get("provider", "unknown") if cache_entry else "unknown"
                model = cache_entry.metadata.get("model", "unknown") if cache_entry else "unknown"
                sources = cache_entry.metadata.get("sources", []) if cache_entry else []

                # Cache hit skips RAG, prompt build, provider selection/switch and LLM call
                _skip_step("rag_search", 4, {"reason": "cache_hit", "query": user_query})
                _skip_step("prompt_build", 5, {"reason": "cache_hit", "query": user_query})
                _skip_step("provider_select", 6, {"reason": "cache_hit", "provider": provider, "model": model})
                _skip_step("provider_switch", 7, {"reason": "cache_hit", "provider": provider, "model": model})
                _skip_step("llm_call", 8, {"reason": "cache_hit", "provider": provider, "model": model})

                # 9. Сохранить в память
                _start_step("memory_save", 9)
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
                _finish_step("memory_save", "ok", {
                    "from_cache": True,
                    "query": user_query,
                    "response": cached_response,
                    "provider": provider,
                    "model": model,
                })

                # 10. Записать Execution Trace summary
                _start_step("log_write", 10)
                response_time_ms = int((time.monotonic() - start_time) * 1000)
                _finish_step("log_write", "ok", {
                    "query": user_query,
                    "response": cached_response,
                    "provider": provider,
                    "model": model,
                    "response_time_ms": response_time_ms,
                    "from_cache": True,
                    "rag_used": False,
                    "sources": sources,
                })

                # 11. Вернуть результат
                _start_step("response_return", 11)
                if self.tracing_service and execution_id:
                    self.tracing_service.set_session_provider(
                        execution_id, provider_key=provider, model_name=model
                    )
                    self.tracing_service.finish_session(
                        execution_id,
                        "ok",
                        {
                            "query": user_query,
                            "response": cached_response,
                            "cache_hit": True,
                            "rag_used": False,
                            "sources": sources,
                            "response_time_ms": response_time_ms,
                        },
                    )
                _finish_step("response_return", "ok", {
                    "query": user_query,
                    "response": cached_response,
                    "provider": provider,
                    "model": model,
                    "cache_hit": True,
                    "rag_used": False,
                    "response_time_ms": response_time_ms,
                })

                return ChatResponseDTO(
                    answer=cached_response,
                    session_id=session_id,
                    user_id=visitor_id,
                    visitor_id=visitor_id,
                    provider=provider,
                    model=model,
                    cache_hit=True,
                    rag_used=False,
                    sources=sources,
                    latency_ms=response_time_ms,
                    metadata={"from_cache": True},
                )

            _finish_step("cache_check", "ok", {"cache_hit": False, "query": user_query})

            # 4. Поиск в Knowledge Base (RAG)
            rag_context = ""
            rag_results = []
            rag_used = False
            sources: list[str] = []

            if self.rag_service.count_documents() > 0:
                _start_step("rag_search", 4)
                rag_results = self.rag_service.search(user_query, top_k=self.rag_top_k)
                if rag_results:
                    rag_context = self.rag_service.get_context(user_query, top_k=self.rag_top_k)
                    rag_used = True
                    sources = [r.source for r in rag_results]
                    _finish_step("rag_search", "ok", {
                        "sources_count": len(sources),
                        "sources": sources,
                        "query": user_query,
                        "rag_used": True,
                    })
                else:
                    _finish_step("rag_search", "ok", {"sources_count": 0, "query": user_query, "rag_used": False})
            else:
                _skip_step("rag_search", 4, {"reason": "no_documents", "query": user_query})

            # 5. Сформировать prompt
            _start_step("prompt_build", 5)
            prompt = self.prompt_assembly.build(
                user_query=user_query,
                conversation_memory=conversation_memory,
                rag_context=rag_context if rag_context else None,
            )
            _finish_step("prompt_build", "ok", {
                "rag_used": rag_used,
                "query": user_query,
                "sources": sources,
                "sources_count": len(sources),
            })

            # 6. Выбрать активного AI Provider
            _start_step("provider_select", 6)
            active_row, warnings = self.provider_settings.get_effective_provider()
            fallback_at_select = False

            if not active_row:
                fallback_row = self.provider_settings.get_fallback()
                if fallback_row:
                    active_row = fallback_row
                    fallback_at_select = True
                    # Логируем переключение
                    self.log_service.log_provider_switch(
                        provider_key=fallback_row.provider_key,
                        model_name=fallback_row.model_name or "unknown",
                        status="ok",
                        metadata={"reason": "No active provider, using fallback"},
                    )
                else:
                    _finish_step("provider_select", "error", {
                        "error": "No AI provider available",
                        "query": user_query,
                    })
                    response_time_ms = int((time.monotonic() - start_time) * 1000)
                    _finalize("error", {"error": "No AI provider available"})

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
                        metadata={"error": "No AI provider available"},
                    )

            active_config = self.provider_settings.build_effective_config(active_row)
            provider_key = active_config.provider_key
            model_name = active_config.model_name or "unknown"
            _finish_step("provider_select", "ok", {
                "fallback_at_select": fallback_at_select,
                "provider": provider_key,
                "model": model_name,
                "query": user_query,
            })

            # 7. Provider switch step
            if fallback_at_select:
                _start_step("provider_switch", 7, {"provider": provider_key, "model": model_name})
                _finish_step("provider_switch", "ok", {
                    "reason": "No active provider",
                    "provider": provider_key,
                    "model": model_name,
                })
            else:
                _skip_step("provider_switch", 7, {
                    "reason": "primary_available",
                    "provider": provider_key,
                    "model": model_name,
                })

            # 8. Выполнить запрос к LLM (с failover)
            answer = None
            provider_used = provider_key
            model_used = model_name
            fallback_used = False
            error_message = None

            _start_step("llm_call", 8, {
                "provider": provider_key,
                "model": model_name,
                "query": user_query,
                "rag_used": rag_used,
            })
            try:
                provider = AIProviderFactory.create(provider_key, config=active_config)
                llm_start = time.monotonic()
                answer = await provider.generate(
                    prompt,
                    temperature=active_config.temperature,
                    max_tokens=active_config.max_tokens,
                )
                llm_latency_ms = int((time.monotonic() - llm_start) * 1000)
                _finish_step("llm_call", "ok", {
                    "provider": provider_key,
                    "model": model_name,
                    "latency_ms": llm_latency_ms,
                    "query": user_query,
                    "rag_used": rag_used,
                })

            except Exception as e:
                # Primary failed
                _finish_step("llm_call", "error", {
                    "error": str(e),
                    "provider": provider_key,
                    "model": model_name,
                    "query": user_query,
                })
                error_message = str(e)

                fallback_row = self.provider_settings.get_fallback()
                if fallback_row:
                    # Record provider switch and retry
                    _start_step("provider_switch", 7)
                    fallback_config = self.provider_settings.build_effective_config(fallback_row)
                    fallback_used = True
                    provider_used = fallback_config.provider_key
                    model_used = fallback_config.model_name or "unknown"

                    try:
                        provider = AIProviderFactory.create(
                            fallback_config.provider_key, config=fallback_config
                        )
                        llm_start = time.monotonic()
                        answer = await provider.generate(
                            prompt,
                            temperature=fallback_config.temperature,
                            max_tokens=fallback_config.max_tokens,
                        )
                        llm_latency_ms = int((time.monotonic() - llm_start) * 1000)

                        # Логируем переключение провайдера
                        self.log_service.log_provider_switch(
                            provider_key=fallback_config.provider_key,
                            model_name=fallback_config.model_name or "unknown",
                            status="ok",
                            metadata={"reason": f"Primary provider failed: {error_message}"},
                        )
                        _finish_step("provider_switch", "ok", {
                            "reason": f"Primary failed: {error_message}",
                            "provider": provider_used,
                            "model": model_used,
                        })

                        # Retry LLM call
                        _start_step("llm_call", 8, {
                            "provider": provider_used,
                            "model": model_used,
                            "retry": True,
                            "query": user_query,
                            "rag_used": rag_used,
                        })
                        _finish_step("llm_call", "ok", {
                            "provider": provider_used,
                            "model": model_used,
                            "latency_ms": llm_latency_ms,
                            "retry": True,
                            "query": user_query,
                            "rag_used": rag_used,
                        })

                    except Exception as fallback_error:
                        _finish_step("llm_call", "error", {
                            "error": str(fallback_error),
                            "provider": provider_used,
                            "model": model_used,
                            "retry": True,
                            "query": user_query,
                        })
                        # Fallback тоже не сработал
                        error_message = f"Both primary and fallback providers failed. Primary: {error_message}. Fallback: {fallback_error}"
                        answer = self._get_error_response(error_message)
                        _finish_step("provider_switch", "error", {
                            "error": str(fallback_error),
                            "provider": provider_used,
                            "model": model_used,
                        })
                else:
                    # No fallback available
                    answer = self._get_error_response(error_message)

            # 9. Сохранить в кеш
            _start_step("memory_save", 9)
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

            # 10. Сохранить в память
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
            _finish_step("memory_save", "ok", {
                "query": user_query,
                "response": answer,
                "provider": provider_used,
                "model": model_used,
                "rag_used": rag_used,
                "sources": sources,
            })

            # 11. Записать Execution Trace summary
            _start_step("log_write", 10)
            response_time_ms = int((time.monotonic() - start_time) * 1000)

            _finish_step("log_write", "ok", {
                "query": user_query,
                "response": answer,
                "provider": provider_used,
                "model": model_used,
                "response_time_ms": response_time_ms,
                "rag_used": rag_used,
                "sources": sources,
                "fallback_used": fallback_used,
                "error": error_message,
            })

            # 12. Вернуть результат
            _start_step("response_return", 11)
            final_status = "error" if error_message else "ok"
            if self.tracing_service and execution_id:
                self.tracing_service.set_session_provider(
                    execution_id, provider_key=provider_used, model_name=model_used
                )
                self.tracing_service.set_session_route(
                    execution_id, route="rag" if rag_used else "text"
                )
                self.tracing_service.finish_session(
                    execution_id,
                    final_status,
                    {
                        "query": user_query,
                        "response": answer,
                        "rag_used": rag_used,
                        "fallback_used": fallback_used,
                        "error": error_message,
                        "sources": sources,
                        "response_time_ms": response_time_ms,
                    },
                )
            _finish_step("response_return", final_status, {
                "query": user_query,
                "response": answer,
                "provider": provider_used,
                "model": model_used,
                "rag_used": rag_used,
                "cache_hit": False,
                "fallback_used": fallback_used,
                "response_time_ms": response_time_ms,
                "error": error_message,
            })

            return ChatResponseDTO(
                answer=answer,
                session_id=session_id,
                user_id=visitor_id,
                visitor_id=visitor_id,
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

        except Exception as e:
            # Unexpected failure: mark any running step and the session as error,
            # then re-raise so the caller still receives the exception.
            if self.tracing_service and execution_id:
                for step_id in step_ids.values():
                    try:
                        self.tracing_service.finish_step(
                            step_id, "error", {"error": str(e)}
                        )
                    except Exception:
                        pass
                try:
                    self.tracing_service.finish_session(
                        execution_id, "error", {"error": str(e)}
                    )
                except Exception:
                    # If finishing the session fails (e.g. DB transaction issue),
                    # try to mark it as error directly so it does not stay "running".
                    try:
                        execution = self.tracing_service._db.get(
                            ExecutionSession, execution_id
                        )
                        if execution:
                            execution.status = "error"
                            execution.execution_metadata = {
                                **(execution.execution_metadata or {}),
                                "error": str(e),
                            }
                            self.tracing_service._db.commit()
                    except Exception:
                        pass
            raise

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