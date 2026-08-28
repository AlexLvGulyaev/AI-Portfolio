"""
Chat Orchestrator для AI Portfolio.

Центральный сервис, управляющий жизненным циклом обработки запроса.

Pipeline:
1. Определить сессию
2. Загрузить память
3. Выбрать активного AI Provider (до кеша — fingerprint ключа зависит от
   провайдера/модели)
4. Проверить Response Cache (версионированный fingerprint-ключ)
5. Детерминированные маршруты (листинг/счёт портфеля — без LLM)
6. При Cache Miss — выполнить поиск в Knowledge Base (проект-scoped или
   диверсифицированный для межпроектных вопросов) — ровно один retrieval
7. Сформировать контекст из полученных результатов
8. Выполнить запрос к LLM (с failover)
9. Сохранить ответ
10. Записать Operational Log
11. Вернуть результат

Источники:
- Assistant Flow: pipeline обработки запроса
- Review Flow: интеграция сервисов
- PEcf09: RAG integration
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.response import ChatResponseDTO
from app.services.ai_provider_settings_service import AIProviderSettingsService
from app.services import eval_trace as eval_trace_mod
from app.services.cache.response_cache import ResponseCache
from app.services.chat_session_service import ChatSessionService
from app.services.conversation_memory_service import ConversationMemoryService
from app.services.execution_tracing_service import ExecutionTracingService
from app.services.operational_log_service import OperationalLogService
from app.services.portfolio_registry import RegistryCard
from app.services.prompt_assembly import PromptAssembly
from app.services.providers.base import AIProvider
from app.services.providers.factory import AIProviderFactory
from app.services.rag.rag_service import RAGService


# Анафорические ссылки («у него», «этот проект»): текущий запрос не содержит
# сущности, поэтому retrieval-запрос обогащается последним пользовательским
# сообщением, в котором реестр находит проект. Только retrieval — не промпт.
ANAPHORA_RE = re.compile(
    r"\b(у него|него|нему|её|ей|этот|эта|это|этого|этой|этих|их|ним|ней|"
    r"оба|обе|тот же|та же|те же)\b",
    re.IGNORECASE,
)


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
        rag_top_k: int = 6,
    ):
        """
        Инициализация ChatOrchestrator.

        Args:
            db: Сессия базы данных
            cache: Сервис кеширования
            rag_service: Сервис RAG
            tracing_service: Опциональный сервис execution tracing
            cache_ttl_seconds: Время жизни кеша
            rag_top_k: Количество чанков для retrieval (scoped/global)
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
        self.log_service = OperationalLogService(db)
        self.prompt_assembly = PromptAssembly()
        # Детерминированный реестр портфеля (SOT — project_cards).
        from app.services.portfolio_registry import PortfolioRegistry

        self.registry = PortfolioRegistry(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _config_fingerprint(self, provider_key: str, model_name: str) -> str:
        """
        Версионный fingerprint конфигурации для cache-ключа.

        Смена коллекции/KB, системного промпта, retrieval-конфигурации или
        провайдера/модели меняет ключ — старые ответы не выдаются.
        """
        collection = getattr(self.rag_service.config, "collection_name", "?")
        return (
            f"col:{collection}"
            f"|{PromptAssembly.fingerprint()}"
            f"|retrieval:top_k={self.rag_top_k}"
            f"|{provider_key}/{model_name}"
        )

    @staticmethod
    def _is_refusal(answer: str) -> bool:
        """
        Определяет канонический grounded-refusal ответ.

        Формулировка задана системным промптом (правило 2). Такие ответы не
        кешируются: LLM может отказать стохастически при релевантном контексте,
        и кеш зафиксировал бы неудачный исход для всех новых сессий.
        """
        return "такой информации нет" in (answer or "").lower()

    @staticmethod
    def _citations(rag_results: list) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Пользовательские цитаты: `<repository> · <relative path>`.

        Дедупликация по repository+path с сохранением порядка первого
        появления. Возвращает (sources, sources_detail).
        """
        seen: set[str] = set()
        sources: list[str] = []
        detail: list[dict[str, Any]] = []
        for r in rag_results:
            repo = r.metadata.get("repo")
            path = r.metadata.get("path") or r.source
            label = f"{repo} · {path}" if repo else path
            if label not in seen:
                seen.add(label)
                sources.append(label)
            detail.append({
                "repo": repo,
                "path": path,
                "chunk_index": r.metadata.get("chunk_index"),
                "score": r.score,
            })
        return sources, detail

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

        # Diagnostic eval tracing (opt-in, disabled by default; never alters behavior).
        _tr: eval_trace_mod.EvalTrace | None = (
            eval_trace_mod.EvalTrace(query=user_query) if eval_trace_mod.is_enabled() else None
        )
        _t_retrieval_ms: list[int] = []
        _t_llm_ms: list[int] = []

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

            # Ответ с историей не кешируется: закешированный ответ сгенерирован
            # без учёта контекста этого диалога (устраняет кросс-сессионное
            # загрязнение и дрейф от истории).
            history_present = len(conversation_memory) > 0

            if _tr is not None:
                _tr.set("session_id", str(session_id))
                _tr.set("history_messages", [
                    {"role": m.role, "content": m.content} for m in conversation_memory
                ])
                _tr.set("history_count", len(conversation_memory))
                _tr.set("history_roles", [m.role for m in conversation_memory])
                _tr.set("cache_bypass", history_present)

            # 3. Выбрать активного AI Provider (до cache-проверки: fingerprint
            # ключа кеша включает провайдера/модель)
            _start_step("provider_select", 3)
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

                    if _tr is not None:
                        _tr.set("answer", None)
                        _tr.set("provider", "none")
                        _tr.set("model", "none")
                        _tr.set_error("No AI provider available")
                        _tr.finish(response_time_ms)

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

            config_fingerprint = self._config_fingerprint(provider_key, model_name)

            # 4. Проверить Response Cache (версионированный ключ)
            _start_step("cache_check", 4)
            cached_response = None
            cache_entry = None
            if not history_present:
                if _tr is not None:
                    _tr.set("cache_key", self.cache.get_cache_key(user_query, config_fingerprint))
                    _tr.set("cache_file", str(self.cache.cache_file))
                cached_response = self.cache.get(user_query, fingerprint=config_fingerprint)
            if _tr is not None:
                _tr.set("cache_hit", bool(cached_response))
            if cached_response:
                # Получить метаданные из кеша
                cache_entry = self.cache.get_entry(user_query, fingerprint=config_fingerprint)
                provider = cache_entry.metadata.get("provider", provider_key) if cache_entry else provider_key
                model = cache_entry.metadata.get("model", model_name) if cache_entry else model_name
                sources = cache_entry.metadata.get("sources", []) if cache_entry else []

                _finish_step("cache_check", "ok", {
                    "cache_hit": True,
                    "query": user_query,
                    "provider": provider,
                    "model": model,
                })

                # Cache hit skips RAG, prompt build and LLM call
                _skip_step("rag_search", 5, {"reason": "cache_hit", "query": user_query})
                _skip_step("prompt_build", 6, {"reason": "cache_hit", "query": user_query})
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

                if _tr is not None:
                    _tr.set("answer", cached_response)
                    _tr.set("sources_returned", sources)
                    _tr.set("provider", provider)
                    _tr.set("model", model)
                    _tr.set("retrieval_ms", 0)
                    _tr.set("generation_ms", 0)
                    _tr.finish(response_time_ms)

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

            # 4a. Детерминированные маршруты реестра (листинг/счёт портфеля):
            # ответ выводится из project_cards напрямую — без RAG, без LLM,
            # без истории диалога.
            intent = self.registry.classify(user_query)
            if intent in ("listing", "count"):
                registry_fp = f"registry:{self.registry.version}"
                if _tr is not None:
                    _tr.set("route", f"registry_{intent}")
                    _tr.set("registry_version", self.registry.version)
                _skip_step("rag_search", 5, {"reason": f"deterministic_{intent}", "query": user_query})
                _skip_step("prompt_build", 6, {"reason": f"deterministic_{intent}", "query": user_query})
                _skip_step("provider_switch", 7, {"reason": "deterministic_route"})
                _skip_step("llm_call", 8, {"reason": f"deterministic_{intent}", "query": user_query})

                # Собственный fingerprint кеша: версия реестра
                cached = self.cache.get(user_query, fingerprint=registry_fp)
                if cached:
                    answer = cached
                    cache_hit = True
                else:
                    answer = (
                        self.registry.render_list()
                        if intent == "listing"
                        else self.registry.render_count()
                    )
                    self.cache.set(
                        query=user_query,
                        response=answer,
                        metadata={
                            "provider": provider_key,
                            "model": model_name,
                            "sources": [],
                            "route": f"registry_{intent}",
                        },
                        ttl_seconds=self.cache_ttl_seconds,
                        fingerprint=registry_fp,
                    )
                    cache_hit = False

                # Сохранить в память (для последующих уточняющих вопросов)
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
                    content=answer,
                    metadata={"route": f"registry_{intent}", "from_cache": cache_hit},
                )
                _finish_step("memory_save", "ok", {
                    "route": f"registry_{intent}",
                    "response": answer,
                })

                response_time_ms = int((time.monotonic() - start_time) * 1000)
                _start_step("log_write", 10)
                _finish_step("log_write", "ok", {
                    "query": user_query,
                    "route": f"registry_{intent}",
                    "response": answer,
                    "response_time_ms": response_time_ms,
                    "cache_hit": cache_hit,
                })

                _start_step("response_return", 11)
                if self.tracing_service and execution_id:
                    self.tracing_service.set_session_provider(
                        execution_id, provider_key=provider_key, model_name=model_name
                    )
                    self.tracing_service.set_session_route(execution_id, route="deterministic")
                    self.tracing_service.finish_session(
                        execution_id, "ok",
                        {
                            "query": user_query,
                            "route": f"registry_{intent}",
                            "response": answer,
                            "response_time_ms": response_time_ms,
                        },
                    )
                _finish_step("response_return", "ok", {
                    "query": user_query,
                    "route": f"registry_{intent}",
                    "response": answer,
                    "response_time_ms": response_time_ms,
                })

                if _tr is not None:
                    _tr.set("answer", answer)
                    _tr.set("sources_returned", [])
                    _tr.set("provider", provider_key)
                    _tr.set("model", model_name)
                    _tr.set("retrieval_ms", 0)
                    _tr.set("generation_ms", 0)
                    _tr.finish(response_time_ms)

                return ChatResponseDTO(
                    answer=answer,
                    session_id=session_id,
                    user_id=visitor_id,
                    visitor_id=visitor_id,
                    provider=provider_key,
                    model=model_name,
                    cache_hit=cache_hit,
                    rag_used=False,
                    sources=[],
                    latency_ms=response_time_ms,
                    metadata={
                        "route": f"registry_{intent}",
                        "registry_version": self.registry.version,
                    },
                )

            # 5. Поиск в Knowledge Base (RAG) — ровно один retrieval.
            # Маршрутизация: одноимённый проект → repo-scoped; несколько
            # проектов → диверсифицированный поиск по их репозиториям;
            # вопрос о подмножестве проектов → диверсифицированный поиск по
            # всем репозиториям; иначе — глобальный поиск.
            rag_context = ""
            rag_results = []
            rag_used = False
            sources: list[str] = []
            sources_detail: list[dict[str, Any]] = []
            retrieval_mode = "global"

            resolved_cards: list[RegistryCard] = (
                self.registry.resolve_all(user_query) if intent in ("unknown", "filtered") else []
            )
            # Анафора: запрос без явного проекта («какой у него стек») —
            # обогащаем retrieval-запрос последним сообщением с проектом.
            retrieval_query = user_query
            if (
                not resolved_cards
                and history_present
                and ANAPHORA_RE.search(user_query)
            ):
                for m in reversed(conversation_memory):
                    if m.role != "user":
                        continue
                    prior_cards = self.registry.resolve_all(m.content)
                    if prior_cards:
                        retrieval_query = f"{m.content} | {user_query}"
                        resolved_cards = prior_cards
                        break
            if _tr is not None:
                _tr.set("resolved_cards", [c.slug for c in resolved_cards])
                _tr.set("retrieval_query", retrieval_query)

            if self.rag_service.count_documents() > 0:
                _start_step("rag_search", 5)
                _t0 = time.monotonic()
                if len(resolved_cards) >= 2:
                    # Проект уже сужает корпус — поиск по исходному запросу.
                    retrieval_mode = "diverse"
                    repos = [
                        self.registry.repo_for_card(c) for c in resolved_cards
                    ]
                    repos = [r for r in repos if r] or self.registry.repos
                    rag_results = self.rag_service.search_diverse(
                        user_query,
                        repos=repos,
                        per_repo_k=2,
                        final_top_k=6,
                        max_per_repo=2,
                    )
                elif intent == "filtered":
                    # Подмножество проектов: ограниченный fan-out по всем
                    # допущенным репозиториям — каждый репозиторий гарантированно
                    # даёт свой лучший чанк (иначе сильные репозитории
                    # вытесняют остальные из контекста целиком).
                    retrieval_mode = "diverse_all"
                    rag_results = self.rag_service.search_diverse(
                        user_query,
                        repos=self.registry.repos,
                        per_repo_k=2,
                        final_top_k=12,
                        max_per_repo=1,
                    )
                elif len(resolved_cards) == 1:
                    retrieval_mode = "project_scoped"
                    repo = self.registry.repo_for_card(resolved_cards[0])
                    if repo:
                        rag_results = self.rag_service.search(
                            user_query,
                            top_k=self.rag_top_k,
                            where={"repo": {"$eq": repo}},
                        )
                    if not rag_results:
                        # Проект найден в реестре, но в его KB нет релевантных
                        # чанков — честный fallback в глобальный поиск.
                        retrieval_mode = "global_fallback"
                        rag_results = self.rag_service.search(
                            retrieval_query, top_k=self.rag_top_k
                        )
                else:
                    rag_results = self.rag_service.search(
                        retrieval_query, top_k=self.rag_top_k
                    )
                _t_retrieval_ms.append(int((time.monotonic() - _t0) * 1000))
                if rag_results:
                    # Контекст строится из УЖЕ полученных результатов —
                    # без повторного поиска (один retrieval на запрос).
                    rag_context = self.rag_service.build_context(rag_results)
                    rag_used = True
                    sources, sources_detail = self._citations(rag_results)
                    if _tr is not None:
                        _tr.set("collection", self.rag_service.config.collection_name)
                        _tr.set("kb_chunk_count", self.rag_service.count_documents())
                        _tr.set("retrieval_mode", retrieval_mode)
                        _tr.set("retrieval_ms", _t_retrieval_ms[-1])
                        _tr.set("retrieved_chunks", [
                            {
                                "rank": i + 1,
                                "chunk_id": r.chunk_id,
                                "score_distance": r.score,
                                "source": r.source,
                                "repo": r.metadata.get("repo"),
                                "path": r.metadata.get("path"),
                                "document_id": r.metadata.get("document_id"),
                                "chunk_index": r.metadata.get("chunk_index"),
                                "content_head": eval_trace_mod.content_head(r.content),
                                "content_sha256": eval_trace_mod.content_sha256(r.content),
                            }
                            for i, r in enumerate(rag_results)
                        ])
                        _tr.set("rag_context", rag_context)
                        _tr.set("rag_context_sha256", eval_trace_mod.content_sha256(rag_context))
                    _finish_step("rag_search", "ok", {
                        "retrieval_mode": retrieval_mode,
                        "sources_count": len(sources),
                        "sources": sources,
                        "query": user_query,
                        "rag_used": True,
                    })
                else:
                    _finish_step("rag_search", "ok", {"retrieval_mode": retrieval_mode,
                                                     "sources_count": 0, "query": user_query, "rag_used": False})
            else:
                _skip_step("rag_search", 5, {"reason": "no_documents", "query": user_query})

            # 6. Сформировать prompt (разделение доверенных/недоверенных блоков)
            _start_step("prompt_build", 6)
            prompt = self.prompt_assembly.build(
                user_query=user_query,
                conversation_memory=conversation_memory,
                rag_context=rag_context if rag_context else None,
                registry_list=self.registry.render_list(),
                registry_version=self.registry.version,
            )
            if _tr is not None:
                _tr.set("prompt", prompt)
                _tr.set("prompt_sha256", eval_trace_mod.content_sha256(prompt))
            _finish_step("prompt_build", "ok", {
                "rag_used": rag_used,
                "query": user_query,
                "sources": sources,
                "sources_count": len(sources),
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
                _t_llm_ms.append(llm_latency_ms)
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

            # 9. Сохранить в кеш (только для ответов без истории).
            # Отказные ответы не кешируются: отказ может быть стохастическим
            # (LLM при релевантном контексте), кеш заморозил бы неудачный
            # исход для всех последующих сессий.
            _start_step("memory_save", 9)
            if not history_present and not self._is_refusal(answer):
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
                    fingerprint=config_fingerprint,
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
                "cache_bypass": history_present,
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

            if _tr is not None:
                _tr.set("answer", answer)
                _tr.set("sources_returned", sources)
                _tr.set("provider", provider_used)
                _tr.set("model", model_used)
                _tr.set("retrieval_ms", sum(_t_retrieval_ms))
                _tr.set("generation_ms", _t_llm_ms[-1] if _t_llm_ms else None)
                if error_message:
                    _tr.set_error(error_message)
                _tr.finish(response_time_ms)

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
                    "retrieval_mode": retrieval_mode,
                    "sources_detail": sources_detail,
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
                        from app.models.entities import ExecutionSession

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
            if _tr is not None:
                _tr.set_error(f"unexpected: {e}")
                _tr.finish(int((time.monotonic() - start_time) * 1000))
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