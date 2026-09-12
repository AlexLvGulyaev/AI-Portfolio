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

import concurrent.futures
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
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
from app.services.security.injection_neutralizer import (
    filter_quarantined,
    find_instruction_attacks,
)
from app.models.entities import KnowledgeSource, ProjectCard
from app.services.rag.source_labels import github_blob_url, make_source_label
from app.services.rag.rag_service import RAGService

logger = logging.getLogger(__name__)


class StreamingGenerationError(Exception):
    """Генерация оборвалась после того, как поток уже пошёл зрителю.

    Тихий fallback невозможен (часть ответа уже отдана); маршрут
    публичного стрима переводит это в error-событие SSE, не подменяя
    уже выданный текст.
    """


class _StreamHygieneFilter:
    """Потоковая гигиена дельт (стрим-контур, 10.09.2026).

    Аналог пост-гигиены process_request для потока: цитаты [N] с
    N > числа полученных источников вырезаются до отдачи зрителю,
    языковая метка ограждения (```` ```python ```` у таблиц, кейс
    06.09.2026) срезается до классификации тела, markdown-разметка
    (парные звёздочки, «#»-заголовки, маркеры «* ») срезается как в
    _strip_markdown_emphasis (замечание приёмки 04.09.2026). Хвостовой
    буфер гасит маркеры, разрезанные между дельтами. Финальный текст
    после генерации проходит штатную гигиену (_strip_stale_citations,
    _normalize_table_fences, _strip_markdown_emphasis) — операции
    идемпотентны.
    """

    _CIT = re.compile(r"\[(\d{1,2})\]")
    _FENCE_LABEL = re.compile(r"^```([A-Za-z0-9_+-]*)[^\S\n]*\n")
    _STREAM_HEADING = re.compile(r"^#{1,6}[^\S\n]+(.*)$")
    # сколько символов ждать закрытия звёздочной пары, прежде чем отдать
    # маркер литералом (финальный текст всё равно пройдёт пост-гигиену)
    _STAR_HOLD = 200

    def __init__(self, sources_count: int) -> None:
        self._max_citation = sources_count
        self._buf = ""

    def feed(self, delta: str) -> str:
        """Принять дельту, вернуть гигиеничную часть для отдачи."""
        self._buf += delta
        out: list[str] = []
        while self._buf:
            if self._buf.startswith("```"):
                m = self._FENCE_LABEL.match(self._buf)
                if m:
                    lang = m.group(1).lower()
                    # Метки markdown/md не трогаем (как в
                    # _normalize_table_fences); прочие метки срезаем —
                    # тело таблиц/блоков уходит под plain-ограждением.
                    out.append(m.group(0) if lang in ("", "markdown", "md") else "```\n")
                    self._buf = self._buf[m.end():]
                    continue
                if len(self._buf) <= 10:
                    break  # метка ещё не доплыла до конца строки
                out.append("```")
                self._buf = self._buf[3:]
                continue
            marker, pos = self._next_marker()
            if pos is None:
                out.append(self._buf)
                self._buf = ""
                break
            if pos > 0:
                out.append(self._buf[:pos])
                self._buf = self._buf[pos:]
            if marker == "[":
                m = self._CIT.match(self._buf)
                if m:
                    if m.end() >= len(self._buf):
                        break  # ждём следующий символ для lookahead «(?!\()»
                    if int(m.group(1)) > self._max_citation:
                        self._buf = self._buf[m.end():]
                    else:
                        out.append(self._buf[: m.end()])
                        self._buf = self._buf[m.end():]
                    continue
                if len(self._buf) > 5:
                    # «[» не начал цитату — отдать литерал
                    out.append("[")
                    self._buf = self._buf[1:]
                else:
                    break  # возможная недоплавшая цитата — подождать
            elif marker == "*":
                if not self._feed_star(out):
                    break
            else:  # "#"
                if not self._feed_heading(out):
                    break
        return "".join(out)

    def _next_marker(self) -> "tuple[str, int] | tuple[None, None]":
        """Ближайший гигиеничный маркер в буфере: «[», «*» или «#»."""
        found = [(self._buf.find(ch), ch) for ch in "[*#"]
        found = [(i, ch) for i, ch in found if i != -1]
        return (min(found)[1], min(found)[0]) if found else (None, None)

    def _feed_star(self, out: list[str]) -> bool:
        """Звёздочки в потоке. False — пара не доплыла, ждать дельту."""
        buf = self._buf
        if buf.startswith("**"):
            rest = buf[2:]
            nl, close = rest.find("\n"), rest.find("**")
            if close != -1 and (nl == -1 or close < nl):
                out.append(rest[:close])  # парный жирный → текст
                self._buf = rest[close + 2:]
                return True
            if nl != -1 or len(buf) > self._STAR_HOLD:
                out.append("**")  # непарный (или слишком долгое ожидание) — литерал
                self._buf = rest
                return True
            return False  # ждём закрывающие
        at_line_start = not out or out[-1][-1] == "\n"
        if at_line_start and len(buf) > 1 and buf[1] in " \t":
            out.append("- ")  # маркер списка «* » → «- » (правило 14)
            self._buf = buf[1:].lstrip(" \t")
            return True
        close, nl = buf.find("*", 1), buf.find("\n", 1)
        if close != -1 and (nl == -1 or close < nl):
            content = buf[1:close]
            prev = out[-1][-1] if out else ""
            if self._valid_emphasis(content, prev):
                out.append(content)  # одиночная пара → текст
                self._buf = buf[close + 1:]
            else:
                out.append("*")  # «2*3», пробел у границы — литерал
                self._buf = buf[1:]
            return True
        if nl != -1 or len(buf) > self._STAR_HOLD:
            out.append("*")  # пара не закрылась до конца строки — литерал
            self._buf = buf[1:]
            return True
        return False  # ждём пару или конец строки

    def _feed_heading(self, out: list[str]) -> bool:
        """«#»-заголовок в начале строки → текст. False — ждать дельту."""
        at_line_start = not out or out[-1][-1] == "\n"
        if not at_line_start:
            out.append("#")  # «C#», хештег в строке — литерал
            self._buf = self._buf[1:]
            return True
        nl = self._buf.find("\n")
        if nl == -1:
            if len(self._buf) > self._STAR_HOLD:
                out.append("#")
                self._buf = self._buf[1:]
                return True
            return False  # ждём конец строки, чтобы увидеть строку целиком
        line, self._buf = self._buf[:nl], self._buf[nl + 1:]
        m = self._STREAM_HEADING.match(line)
        out.append(m.group(1) + "\n" if m else line + "\n")
        return True

    @staticmethod
    def _valid_emphasis(content: str, prev: str) -> bool:
        """Одиночная пара «*текст*» — эмфаза, не математика/мусор."""
        if not content or content[0] in " \t" or content[-1] in " \t":
            return False
        if prev.isdigit() and content[0].isdigit():
            return False  # умножение «2*3»
        return any(ch.isalpha() for ch in content)

    def flush(self) -> str:
        """Сбросить хвостовой буфер (конец потока)."""
        buf, self._buf = self._buf, ""
        return buf


# Анафорические ссылки («у него», «этот проект»): текущий запрос не содержит
# сущности, поэтому retrieval-запрос обогащается последним пользовательским
# сообщением, в котором реестр находит проект. Только retrieval — не промпт.
ANAPHORA_RE = re.compile(
    r"\b(у него|него|нему|её|ей|этот|эта|это|этого|этой|этих|их|ним|ней|"
    r"оба|обе|тот же|та же|те же)\b",
    re.IGNORECASE,
)

# Безличное «это» в определительных вопросах («что это за …», «что это
# такое») — не анафора: обогащение retrieval прошлым проектом сужало поиск
# не туда. Кейс 03.09: чип «Что это за платформа?» в сессии со старой
# историей про AI Curator → project_scoped-поиск по репозиторию AI-Curator,
# ответ целиком про чужой кейс. Такие вопросы — самодостаточные, retrieval
# идёт по исходному запросу.
IMPERSONAL_ITA_RE = re.compile(r"\bчто\s+это\b", re.IGNORECASE)

# Демонстративная ссылка на текущую страницу («этот кейс», «в этом проекте»)
# при валидном page_slug — ссылка на страницу, не анафора к проекту из
# истории. Кейс 05.09: «Как устроен этот кейс?» на странице Retail Group в
# сессии с прежними вопросами про Assistant Flow → анафора вытесняла
# страницу, retrieval искал в чужом репозитории при верном ответе.
# Единственное и множественное число («этот кейс» … «в этом проекте»).
PAGE_DEMONSTRATIVE_RE = re.compile(
    r"\bэт(?:от|ого|ому|им|ом)\s+(?:кейс\w*|проект\w*)\b",
    re.IGNORECASE,
)

# Мета-вопрос о числах («Какие результаты и метрики?»): эмбеддинг
# притягивает шапки документов и FAQ, а разделы с цифрами написаны без
# слов «результаты/метрики» («Экономия времени», «Стоимость обработки»).
# Кейс 10.09: по запросу «AI Curator | Какие результаты и метрики?» эти
# разделы не поднялись даже в top-40. Мета-вопрос обогащается лексикой
# таких разделов (только retrieval, не промпт).
METRIC_QUERY_RE = re.compile(
    r"\b(?:результат\w*|метрик\w*|показател\w*|цифр\w*|эконом\w*|эффективност\w*)\b",
    re.IGNORECASE,
)
METRIC_QUERY_HINT = (
    " количественная ценность: экономия времени, стоимость, показатели"
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
        include_hidden: bool = False,
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
            include_hidden: канал владельца (admin chat-preview) — retrieval
                guard скрытых проектов не применяется (следствие §5.1 п. 9)
        """
        self.db = db
        self.cache = cache
        self.rag_service = rag_service
        self.tracing_service = tracing_service
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rag_top_k = rag_top_k
        self.include_hidden = include_hidden

        # Инициализируем сервисы
        self.session_service = ChatSessionService(db)
        self.memory_service = ConversationMemoryService(db=db)
        self.provider_settings = AIProviderSettingsService(db)
        self.log_service = OperationalLogService(db)
        self.prompt_assembly = PromptAssembly()
        # Управляемый системный промпт (консоль AI-настройки, migration 021):
        # активная версия из system_prompts, иначе вшитый дефолт
        # (load_active_prompt сам fail-open при недоступности таблицы).
        from app.services.admin.system_prompt_service import load_active_prompt

        prompt_body, prompt_version = load_active_prompt(db)
        if prompt_body:
            self.prompt_assembly = PromptAssembly(
                system_prompt=prompt_body, version=prompt_version
            )
            self.prompt_unavailable = False
        else:
            # Решение B (09.09.2026, PROMPT_ARCHITECTURE §3): БД —
            # единственный runtime-SOT боевого промпта, вшитый текст —
            # seed релизного базлайна. Нет активной строки / таблица
            # недоступна → честная деградация канала (PromptUnavailableError
            # в process_request), НЕ тихий откат на вшитый v8.
            logger.warning(
                "active system prompt unavailable — channel degrades honestly "
                "(decision B, no builtin fallback)"
            )
            self.prompt_assembly = None
            self.prompt_unavailable = True
        # Детерминированный реестр портфеля (SOT — project_cards). Канал
        # владельца (include_hidden) видит скрытые карточки как обычные —
        # иначе prompt-реестр не знает скрытый проект и LLM детерминированно
        # отказывает даже при найденных KB-чанках (проверено live 29.08).
        from app.services.portfolio_registry import PortfolioRegistry

        self.registry = PortfolioRegistry(db, include_hidden=include_hidden)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _runtime_top_k(self) -> int:
        """top_k из ретривал-консоли (runtime tuning), fallback — init-значение."""
        try:
            from app.services.rag.retrieval_manager import get_retrieval_manager

            return int(get_retrieval_manager().effective_tuning()["rag_top_k"])
        except Exception:
            return self.rag_top_k

    def _runtime_tuning_value(self, key: str, fallback):
        """Значение runtime-tuning из ретривал-консоли, fallback при недоступности."""
        try:
            from app.services.rag.retrieval_manager import get_retrieval_manager

            v = get_retrieval_manager().effective_tuning()[key]
            return fallback if v is None else v
        except Exception:
            return fallback

    def _runtime_answer_max_tokens(self, provider_max_tokens: int) -> int:
        """Кап генерации (AF WH-2): min(конфиг провайдера, лимит консоли Retrieval)."""
        cap = self._runtime_tuning_value("rag_answer_max_tokens", None)
        try:
            return max(1, min(int(provider_max_tokens), int(cap)))
        except (TypeError, ValueError):
            return provider_max_tokens

    def _runtime_retrieval_timeout(self) -> int:
        """Жёсткий таймаут retrieval-шага в секундах (AF WH-2)."""
        try:
            return max(5, int(self._runtime_tuning_value("rag_retrieval_timeout", 30)))
        except (TypeError, ValueError):
            return 30

    def _admissible_repos(self, repos: list[str] | None = None) -> list[str]:
        """
        Список репозиториев, допустимых к выдаче в этом канале.

        Публичный чат: registry.public_repos (без скрытых). Канал владельца
        (include_hidden, admin chat-preview): скрытые репозитории отдаются
        как обычные — скрытость регулирует публичную витрину, а не допуск
        источника в KB (§5.1 п. 4 и п. 9).
        """
        if self.include_hidden:
            return list(repos) if repos is not None else list(self.registry.repos)
        return self.registry.public_repos(repos)

    def _config_fingerprint(self, provider_key: str, model_name: str) -> str:
        """
        Версионный fingerprint конфигурации для cache-ключа.

        Смена коллекции/KB, системного промпта, retrieval-конфигурации или
        провайдера/модели меняет ключ — старые ответы не выдаются.
        """
        collection = getattr(self.rag_service.config, "collection_name", "?")
        return (
            f"col:{collection}"
            f"|{self.prompt_assembly.fingerprint()}"
            f"|retrieval:v{self._RETRIEVAL_LOGIC_VERSION}"
            f"|top_k={self.rag_top_k}"
            f"|{provider_key}/{model_name}"
        )

    @staticmethod
    def _is_refusal(answer: str) -> bool:
        """
        Определяет канонический grounded-refusal ответ.

        Формулировки задаёт системный промпт (правило 2) и его
        контекстные вариации («нет такой аббревиатуры» — прод-наблюдение
        04.09.2026). Местоимение модель варьирует стохастически (прод-кейс
        10.09.2026: «этой информации нет» ускользал от гейта — панель
        источников оставалась под отказом), поэтому паттерны вместо
        литералов: якорь на каноническую фразу правила 2 с вариативным
        местоимением, чтобы «информации нет» в постороннем контексте не
        матчился. Такие ответы не кешируются: LLM может отказать
        стохастически при релевантном контексте, и кеш зафиксировал бы
        неудачный исход для всех новых сессий; они же отдаются без
        источников (панель источников под отказом вводит в заблуждение —
        решение владельца 04.09.2026).
        """
        low = (answer or "").lower()
        return any(p.search(low) for p in ChatOrchestrator._REFUSAL_RES)

    @staticmethod
    def _is_repeat_query(user_query: str, conversation_memory: list) -> bool:
        """
        Дословный повтор: текущий запрос уже звучал в этой сессии.

        Нормализация идентична ключу ResponseCache (`response_cache.py`:
        lower + whitespace-схлопывание), поэтому «повтори меня» и «Повтори
        меня» — один запрос и один ключ кеша. Используется для чтения кеша
        на повторах внутри сессии (вариант А, решение владельца 04.09.2026).
        """
        normalized = " ".join((user_query or "").lower().split())
        if not normalized:
            return False
        return any(
            " ".join((m.content or "").lower().split()) == normalized
            for m in conversation_memory
            if getattr(m, "role", None) == "user"
        )

    def _citations(self, rag_results: list) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Пользовательские цитаты: `<имя проекта> · <короткое имя документа>`
        (вариант C, решение владельца 02.09.2026 — подписи вместо сырых
        GitHub-путей) + GitHub blob-ссылка в detail для кликабельных карточек.

        Дедупликация по (repository, path) с сохранением порядка первого
        появления. Возвращает (sources, sources_detail).
        """
        source_info = self._source_info({
            r.metadata.get("repo")
            for r in rag_results
            if r.metadata.get("repo")
        })
        return self._build_citations(rag_results, source_info)

    # Версия retrieval-логики в fingerprint cache-ключа: правка кода
    # retrieval (кейс 10.09 — демоция шапок + мета-ход) должна отстроить
    # старые ответы, собранные на прежнем составе контекста. При каждом
    # изменении логики retrieval увеличивать.
    _RETRIEVAL_LOGIC_VERSION = 2

    @staticmethod
    def _dedup_by_doc(rag_results: list) -> list:
        """Дедупликация retrieval по (repo, path) — лучший чанк документа.

        Сохраняет порядок первого появления (сортировку по score). Дедуп
        цитат в _build_citations работает только по выдаче, а не по составу
        контекста — поэтому для project_scoped он не спасает.

        Демоция шапок (кейс 10.09): если первый чанк документа —
        только-титульный (H1 + метабойлерплейт, ответить по нему нельзя),
        слот документа уходит первому содержательному чанку того же
        документа в выдаче.
        """
        slot_by_key: dict[tuple[str | None, str], int] = {}
        out = []
        for r in rag_results:
            key = (r.metadata.get("repo"), r.metadata.get("path") or r.source)
            slot = slot_by_key.get(key)
            if slot is None:
                slot_by_key[key] = len(out)
                out.append(r)
            elif (
                ChatOrchestrator._is_title_only_chunk(out[slot])
                and not ChatOrchestrator._is_title_only_chunk(r)
            ):
                out[slot] = r
        return out

    # Метабойлерплейт шапки документа: «Проект: …», «Дата: …», «Статус: …»
    _HEAD_META_LINE_RE = re.compile(
        r"^\s*(?:проект|дата|статус|версия|repo|репозиторий|автор|обновлено)\s*:",
        re.IGNORECASE,
    )

    @classmethod
    def _is_title_only_chunk(cls, r) -> bool:
        """Только-титульный чанк: chunk_index 0, после заголовка — только
        метабойлерплейт «Ключ: значение». Контента в таком чанке нет,
        ответить по нему нельзя."""
        md = getattr(r, "metadata", None) or {}
        if md.get("chunk_index", 1) != 0:
            return False
        lines = [ln.strip() for ln in (r.content or "").splitlines() if ln.strip()]
        if len(lines) < 2:
            return False
        return all(cls._HEAD_META_LINE_RE.match(ln) for ln in lines[1:])

    @classmethod
    def _build_citations(
        cls,
        rag_results: list,
        source_info: dict[str, tuple[str, str | None]],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Чистая сборка цитат по готовому маппингу repo -> (имя, branch)."""
        seen: set[tuple[str | None, str]] = set()
        sources: list[str] = []
        detail: list[dict[str, Any]] = []
        for r in rag_results:
            repo = r.metadata.get("repo")
            path = r.metadata.get("path") or r.source
            key = (repo, path)
            name, branch = source_info.get(repo) or (None, None)
            if name or repo:
                label = make_source_label(name or repo, path)
            else:
                label = path
            # blob-ссылка только при известной ветке из реестра допуска:
            # угаданная ветка — источник битых ссылок (fail-closed).
            html_url = (
                github_blob_url(repo, branch, path)
                if repo and path and branch
                else None
            )
            if key not in seen:
                seen.add(key)
                sources.append(label)
            detail.append({
                "repo": repo,
                "path": path,
                "chunk_index": r.metadata.get("chunk_index"),
                "score": r.score,
                "label": label,
                "html_url": html_url,
                # Полный текст цитированного чанка — панель документа
                # (03.09.2026) ищет его в md на GitHub и подсвечивает.
                "excerpt": re.sub(r"\s+", " ", (r.content or "")).strip()[:2000],
            })
        return sources, detail

    def _source_info(
        self, repos: set[str]
    ) -> dict[str, tuple[str, str | None]]:
        """
        Маппинг `owner/repo` -> (читабельное имя проекта, ветка) из реестра
        допуска: display_name источника, фолбэк — title карточки проекта.
        """
        if not repos:
            return {}
        rows = (
            self.db.query(
                KnowledgeSource.identifier,
                KnowledgeSource.display_name,
                KnowledgeSource.branch,
                ProjectCard.title,
            )
            .outerjoin(
                ProjectCard,
                KnowledgeSource.project_card_id == ProjectCard.id,
            )
            .filter(
                KnowledgeSource.source_type == "github_repo",
                KnowledgeSource.identifier.in_(repos),
            )
            .all()
        )
        return {
            identifier: (display_name or card_title or identifier, branch)
            for identifier, display_name, branch, card_title in rows
        }

    # Цитата-маркер «[N]», за которой НЕ следует «(» (не ломаем markdown-ссылки
    # вида «[1](https://...)»). Двузначных номеров достаточно: top_k ≤ 10.
    _CITATION_RE = re.compile(r"\[(\d{1,2})\](?!\()")

    # Ограждение ```lang ... ``` с содержимым (языковая метка опциональна).
    _FENCE_RE = re.compile(r"```(\w*)[^\S\n]*\n(.*?)```", re.DOTALL)

    # Гейт отказа: канонические фразы правила 2 с вариативным местоимением
    # (прод-кейс 10.09.2026: модель пишет «этой информации нет» наряду с
    # «такой» — литеральный матч оставлял источники под отказом).
    _REFUSAL_RES = (
        re.compile(r"\b(?:такой|этой|подобной) информации нет\b"),
        re.compile(r"\b(?:такой|этой) аббревиатуры нет\b"),
    )

    # Демо-намерение в вопросе (гейт блока ФОРМА ОТВЕТА, кейс 07.09.2026:
    # «Где сейчас мой заказ?» на странице Retail Group уводился в
    # демо-маршрут через триггер «куда пойти»). Явные формулировки:
    # демо/demo, маршрут, «что проверить», «куда пойти», попробовать,
    # стенд, ознакомиться.
    _DEMO_INTENT_RE = re.compile(
        r"демо|demo|маршрут|что\s+проверить|куда\s+пойти|попробовать|стенд|ознакомиться",
        re.IGNORECASE,
    )

    @classmethod
    def _has_demo_intent(cls, user_query: str | None) -> bool:
        """Явное демо-намерение: блок ФОРМА ОТВЕТА (демо-маршрут) попадает
        в промпт только для таких вопросов — детерминированный гейт в коде,
        а не промпт-инженерия, которую модель может обойти."""
        return bool(user_query and cls._DEMO_INTENT_RE.search(user_query))

    # Личные статус-вопросы (не о кейсе): «Где сейчас мой заказ?», «статус
    # моего заказа», «моя заявка». Кейс 07.09.2026: page-обогащение промпта
    # (КОНТЕКСТ/ФОРМА/ОПОРА) на Retail Group уводило такой вопрос в
    # демо-маршрут, а ОПОРА ОТВЕТА — в пересказ сценариев кейса. Пятничный
    # эталон (04.09: честный отказ + описание кейса) получен без
    # page-обогащения — для личных вопросов оно пропускается.
    _PERSONAL_STATUS_RE = re.compile(
        r"мой\s+заказ|моего\s+заказа|моя\s+заявка|моей\s+заявк",
        re.IGNORECASE,
    )

    @classmethod
    def _is_personal_status_query(cls, user_query: str | None) -> bool:
        """Личный статус-вопрос пользователя (не о кейсе)."""
        return bool(user_query and cls._PERSONAL_STATUS_RE.search(user_query))

    @classmethod
    def _normalize_table_fences(cls, answer: str) -> str:
        """
        Срезать языковую метку ограждения, если блок — markdown-таблица
        (GigaChat оборачивает таблицы в ```python```, и фронтенд рендерит
        их как код, кейс 06.09.2026: таблица LoRA vs GPT как «python»).
        Первая непустая строка блока начинается с «|» → это таблица;
        метки markdown/md не трогаем.
        """
        if not answer or "```" not in answer or "|" not in answer:
            return answer

        def _sub(m: "re.Match[str]") -> str:
            lang, body = m.group(1).lower(), m.group(2)
            if not lang or lang in ("markdown", "md"):
                return m.group(0)
            first = next(
                (ln for ln in body.splitlines() if ln.strip()), "")
            if first.lstrip().startswith("|"):
                return "```\n" + body + "```"
            return m.group(0)

        return cls._FENCE_RE.sub(_sub, answer)

    _HEADING_RE = re.compile(r"^(\s*)#{1,6}[^\S\n]+(.*)$")
    _STAR_BULLET_RE = re.compile(r"^(\s*)\*[^\S\n]+")
    _BOLD_PAIR_RE = re.compile(r"\*\*([^*\n]+)\*\*")
    _STAR_PAIR_RE = re.compile(r"\*([^*\n]{1,80}?)\*")

    @classmethod
    def _strip_markdown_emphasis(cls, answer: str) -> str:
        """
        Срезать markdown-разметку, которую виджет рендерит сырым текстом
        (замечание приёмки 04.09.2026: сырые звёздочки «**Backend:**» и
        заголовки «# Маршрут…» в ответах; правило 14 уже требует отвечать
        без разметки — здесь детерминированная страховка в коде).

        - «#»-заголовки в начале строки → текст (содержимое сохраняется);
        - маркер списка «* » в начале строки → «- » (стиль правила 14);
        - парный жирный «**текст**» и одиночная парная эмфаза «*текст*»
          → текст; одиночная пара признаётся эмфазой только когда внутри
          есть буква и нет пробелов у границ — «2*3», «3*4*5», «2 * 3»
          (умножение) не трогаются;
        - непарные «**» срезаются (незакрытый жирный всё равно виден
          зрителю как мусор).
        """
        if not answer or ("*" not in answer and "#" not in answer):
            return answer

        lines = []
        for ln in answer.split("\n"):
            ln = cls._HEADING_RE.sub(r"\1\2", ln)
            ln = cls._STAR_BULLET_RE.sub(r"\1- ", ln)
            lines.append(ln)
        text = "\n".join(lines)

        text = cls._BOLD_PAIR_RE.sub(r"\1", text)

        def _single(m: "re.Match[str]") -> str:
            content = m.group(1)
            start = m.start()
            prev = text[start - 1] if start else "\n"
            if content[0] in " \t" or content[-1] in " \t":
                return m.group(0)
            if prev.isdigit() and content[0].isdigit():
                return m.group(0)  # умножение «2*3»
            if not any(ch.isalpha() for ch in content):
                return m.group(0)  # «2*3», «***» — не эмфаза
            return content

        text = cls._STAR_PAIR_RE.sub(_single, text)
        return text.replace("**", "")

    @classmethod
    def _strip_stale_citations(cls, answer: str, sources_count: int) -> tuple[str, list[int]]:
        """
        Вырезать цитаты [N] с N > sources_count (дефект «цитаты за пределами
        топ-5»: модель нумерует источники, которых не получала, и UI не может
        разрешить ссылку). Вырезанные номера возвращаются для метаданных;
        артефакты («, )», пустые скобки) зачищаются.
        """
        if not answer or sources_count >= 99 or "[" not in answer:
            return answer, []
        stripped: list[int] = []

        def _sub(m: "re.Match[str]") -> str:
            n = int(m.group(1))
            if n > sources_count:
                stripped.append(n)
                return ""
            return m.group(0)

        cleaned = cls._CITATION_RE.sub(_sub, answer)
        if stripped:
            cleaned = re.sub(r",\s*\)", ")", cleaned)
            cleaned = re.sub(r"\(\s*см\.?\s*\)", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\(\s*\)", "", cleaned)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned, stripped

    async def process_request(
        self,
        user_query: str,
        session_id: uuid.UUID | None = None,
        visitor_id: uuid.UUID | str | None = None,
        page_slug: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        on_token: "Callable[[str], Awaitable[None]] | None" = None,
    ) -> ChatResponseDTO:
        """
        Обрабатывает запрос пользователя.

        Args:
            user_query: Запрос пользователя
            session_id: ID сессии (если None, создаётся новая)
            visitor_id: ID посетителя (если None, создаётся новый)
            page_slug: Slug кейс-страницы, с которой задан вопрос (контекст
                «этот кейс»); принимается только при совпадении с реестром
            client_ip: IP-адрес клиента
            user_agent: User-Agent клиента
            on_token: Стрим-коллбэк (10.09.2026): если задан, генерация
                идёт через generate_stream и каждая гигиеничная дельта
                уходит в коллбэк; финальный ответ собирается из дельт.
                Cache-hit и детерминированные маршруты коллбэк не вызывают
                (маршрут стрима отдаёт полный ответ одним дельта-событием).

        Returns:
            ChatResponseDTO с ответом и метаданными
        """
        start_time = time.monotonic()
        execution_id: uuid.UUID | None = None
        step_ids: dict[str, uuid.UUID] = {}

        # Честная деградация (решение B, 09.09.2026): без активного
        # управляемого промпта канал не отвечает — ни вшитым, ни чем-либо
        # ещё; маршрут публичного чата/preview переводит это в HTTP 503.
        if getattr(self, "prompt_unavailable", False):
            from app.services.admin.system_prompt_service import PromptUnavailableError

            raise PromptUnavailableError(
                "active system prompt is not loaded (no active row in system_prompts)"
            )

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
            # Исключение (решение владельца 04.09.2026, вариант А): дословный
            # повтор вопроса в той же сессии — на него кеш читается. Первый
            # задав этого вопроса прошёл как запрос без истории и записал
            # ответ в кеш; повтор идентичного запроса детерминирован и не
            # зависит от контекста, генерировать его заново незачем.
            repeat_in_session = self._is_repeat_query(user_query, conversation_memory)

            if _tr is not None:
                _tr.set("session_id", str(session_id))
                _tr.set("history_messages", [
                    {"role": m.role, "content": m.content} for m in conversation_memory
                ])
                _tr.set("history_count", len(conversation_memory))
                _tr.set("history_roles", [m.role for m in conversation_memory])
                _tr.set("repeat_in_session", repeat_in_session)
                _tr.set("cache_bypass", history_present and not repeat_in_session)

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
            # Контекст страницы входит в fingerprint: один и тот же вопрос с
            # разных кейс-страниц («этот кейс») не должен коллайдить в кеше.
            if page_slug and self.registry.get_by_slug(page_slug):
                config_fingerprint = f"{config_fingerprint}|page:{page_slug}"

            # 4. Проверить Response Cache (версионированный ключ)
            _start_step("cache_check", 4)
            cached_response = None
            cache_entry = None
            if not history_present or repeat_in_session:
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
                # Явное отрицание для названной скрытой карточки (класс H,
                # owner decision 29.08.2026): вопрос существования «есть ли
                # в портфолио проект X?» о скрытой карточке не деградирует
                # в перечисление витрины.
                hidden_title = self.registry.resolve_hidden(user_query)
                route = (
                    "registry_hidden_absent"
                    if hidden_title
                    else f"registry_{intent}"
                )
                if _tr is not None:
                    _tr.set("route", route)
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
                    if hidden_title is not None:
                        answer = self.registry.render_hidden_absent(hidden_title)
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
                            "route": route,
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
                    metadata={"route": route, "from_cache": cache_hit},
                )
                _finish_step("memory_save", "ok", {
                    "route": route,
                    "response": answer,
                })

                response_time_ms = int((time.monotonic() - start_time) * 1000)
                _start_step("log_write", 10)
                _finish_step("log_write", "ok", {
                    "query": user_query,
                    "route": route,
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
                            "route": route,
                            "response": answer,
                            "response_time_ms": response_time_ms,
                        },
                    )
                _finish_step("response_return", "ok", {
                    "query": user_query,
                    "route": route,
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
                        "route": route,
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
            # Страница кейса (аудит 03.09, решение владельца): валидный slug
            # работает как явно названный проект — retrieval сужается на репо
            # страницы (project_scoped с честным fallback в глобальный поиск).
            # Сырой текст клиента не пробрасывается: в retrieval и промпт идёт
            # только доверенная карточка реестра. Скрытые карточки в публичном
            # канале в реестре отсутствуют (visibility guard 29.08.2026), поэтому
            # page_card здесь — только публичные проекты. page_card вычисляется
            # до анафоры: демонстративная ссылка «этот кейс/проект» при валидной
            # странице (PAGE_DEMONSTRATIVE_RE) — ссылка на страницу, анафору к
            # истории не запускаем (кейс 05.09, решение владельца). Явно
            # названный проект в текущем запросе приоритетнее страницы.
            page_card = self.registry.get_by_slug(page_slug) if page_slug else None

            # Анафора: запрос без явного проекта («какой у него стек») —
            # обогащаем retrieval-запрос последним сообщением с проектом.
            retrieval_query = user_query
            # Отдельный запрос для project_scoped-ветки: обогащается ТОЛЬКО
            # темой страницы (кейс 06.09.2026, решение владельца — вариант A).
            # Анафорное обогащение (retrieval_query) в project_scoped не
            # попадает — сужение там делает repo-фильтр, запрос остаётся
            # сырым (решение 05.09.2026).
            scoped_query = user_query
            if (
                not resolved_cards
                and history_present
                and ANAPHORA_RE.search(user_query)
                and not IMPERSONAL_ITA_RE.search(user_query)
                and not (page_card and PAGE_DEMONSTRATIVE_RE.search(user_query))
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

            if not resolved_cards and page_card is not None:
                resolved_cards = [page_card]
                # Project-scoped поиск обогащаем темой карточки страницы.
                # Короткий follow-up («Какие результаты и метрики?») без
                # токенов темы внутри крупного репозитория поднимает общие
                # документы вместо документов проекта (кейс 06.09.2026:
                # вопрос по LoRA HRA вытащил prompt_evaluation другого
                # эксперимента).
                scoped_query = f"{page_card.title} | {user_query}"
                retrieval_query = scoped_query
                if _tr is not None:
                    _tr.set("resolved_via_page", page_slug)
                    _tr.set("retrieval_query", retrieval_query)

            # Доступность retrieval-канала (векторная СУБД + провайдер
            # эмбеддингов): недоступность не роняет запрос с 500 — контур
            # деградирует к генерации без контекста (честный отказ в промпте,
            # LLM-failover остаётся доступен). Приёмочное ревью,
            # решение владельца 03.09.2026 (вариант A).
            try:
                kb_count = self.rag_service.count_documents()
                kb_error = None
            except Exception as e:
                kb_count = 0
                kb_error = f"{type(e).__name__}: {e}"
                logger.error(
                    "retrieval channel unavailable (count_documents): %s",
                    kb_error,
                )
                if _tr is not None:
                    _tr.set("retrieval_error", kb_error)

            if kb_count > 0:
                _start_step("rag_search", 5)
                _t0 = time.monotonic()
                # Visibility guard (owner decision 29.08.2026, variant B1):
                # документы скрытых карточек лежат в KB, но публичному чату
                # не отдаются — ни через fan-out по репо, ни через глобальный
                # поиск. Реестр — источник скрытых идентификаторов. Канал
                # владельца (include_hidden, admin chat-preview) смотрит без
                # гварда — это его назначение: проверить скрытый проект
                # до публикации.
                def _do_retrieval() -> list:
                    nonlocal retrieval_mode
                    if self.include_hidden:
                        _guard = None
                    else:
                        _guard = self.registry.public_guard()
                    if len(resolved_cards) >= 2:
                        # Проект уже сужает корпус — поиск по исходному запросу.
                        retrieval_mode = "diverse"
                        repos = [
                            self.registry.repo_for_card(c) for c in resolved_cards
                        ]
                        repos = [r for r in repos if r] or self._admissible_repos()
                        return self.rag_service.search_diverse(
                            user_query,
                            repos=repos,
                            per_repo_k=2,
                            final_top_k=6,
                            max_per_repo=2,
                        )
                    if intent == "filtered":
                        # Подмножество проектов: ограниченный fan-out по всем
                        # допущенным репозиториям — каждый репозиторий гарантированно
                        # даёт свой лучший чанк (иначе сильные репозитории
                        # вытесняют остальные из контекста целиком).
                        retrieval_mode = "diverse_all"
                        return self.rag_service.search_diverse(
                            user_query,
                            repos=self._admissible_repos(),
                            per_repo_k=2,
                            final_top_k=12,
                            max_per_repo=1,
                        )
                    if len(resolved_cards) == 1:
                        retrieval_mode = "project_scoped"
                        repo = self.registry.repo_for_card(resolved_cards[0])
                        if repo:
                            top_k = self._runtime_top_k()
                            # Мета-ход (кейс 10.09): вопрос о цифрах без слов
                            # из самих разделов («результаты и метрики» vs
                            # «Экономия времени») не поднимал разделы с
                            # числами даже в top-40 — запрос обогащается
                            # лексикой таких разделов.
                            search_query = scoped_query
                            if METRIC_QUERY_RE.search(user_query):
                                search_query = f"{scoped_query}{METRIC_QUERY_HINT}"
                                if _tr is not None:
                                    _tr.set("metric_query_hint", True)
                            # Doc-разнообразие: fetch втрое шире + дедуп по
                            # (repo, path) — иначе чанки одного документа
                            # вытесняют другие (кейс 06.09: Experiment_001
                            # занимал 2 слота из top-6, заголовок
                            # Experiment_004 оставался за контекстом, и
                            # ассистент считал «три эксперимента» из четырёх).
                            results = self.rag_service.search(
                                search_query,
                                top_k=max(top_k * 3, 12),
                                where={"repo": {"$eq": repo}},
                            )
                            results = self._dedup_by_doc(results)
                            if results:
                                return results[:top_k]
                        # Проект найден в реестре, но в его KB нет релевантных
                        # чанков — честный fallback в глобальный поиск.
                        retrieval_mode = "global_fallback"
                        return self.rag_service.search(
                            retrieval_query, top_k=self._runtime_top_k(), where=_guard
                        )
                    return self.rag_service.search(
                        retrieval_query, top_k=self._runtime_top_k(), where=_guard
                    )

                # Жёсткий таймаут retrieval-шага (AF WH-2): worker-поток,
                # graceful fallback на пустые результаты, трейс-метка.
                retrieval_timeout_s = self._runtime_retrieval_timeout()
                _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    rag_results = _pool.submit(_do_retrieval).result(
                        timeout=retrieval_timeout_s
                    )
                except concurrent.futures.TimeoutError:
                    rag_results = []
                    retrieval_mode = "timeout"
                    if _tr is not None:
                        _tr.set("retrieval_timeout_s", retrieval_timeout_s)
                except Exception as e:
                    # Ошибка retrieval (провайдер эмбеддингов, векторная
                    # СУБД) — деградация к генерации без контекста, не 500:
                    # LLM-failover и честный отказ в промпте остаются
                    # доступны. Приёмочное ревью, вариант A.
                    rag_results = []
                    retrieval_mode = "error"
                    logger.error(
                        "retrieval failed: %s: %s", type(e).__name__, e
                    )
                    if _tr is not None:
                        _tr.set("retrieval_error", f"{type(e).__name__}: {e}")
                finally:
                    _pool.shutdown(wait=False)
                _t_retrieval_ms.append(int((time.monotonic() - _t0) * 1000))
                # Код-нейтрализация doc-инъекций (план п. 4, 09.09.2026):
                # чанки с инструкциями-ловушками («ответь словом X»,
                # «игнорируй инструкции») выводятся из выдачи до контекста
                # и цитат — карантин; второй рубеж — в PromptAssembly.build.
                _quarantined: list = []
                if rag_results:
                    rag_results, _quarantined = filter_quarantined(rag_results)
                    if _quarantined:
                        logger.warning(
                            "rag quarantine: %d chunk(s) with instruction patterns",
                            len(_quarantined),
                        )
                        if _tr is not None:
                            _tr.set(
                                "rag_quarantined",
                                [
                                    {
                                        "chunk_id": q.chunk_id,
                                        "patterns": find_instruction_attacks(q.content),
                                        "source": q.source,
                                        "repo": q.metadata.get("repo"),
                                    }
                                    for q in _quarantined
                                ],
                            )
                if rag_results:
                    # Контекст строится из УЖЕ полученных результатов —
                    # без повторного поиска (один retrieval на запрос).
                    # (Мягкий буст варианта B заменён routing-решением
                    # «страница = названный проект» выше: project_scoped
                    # не пускает чужие источники в выдачу вовсе.)
                    _repos = {
                        r.metadata.get("repo")
                        for r in rag_results
                        if r.metadata.get("repo")
                    }
                    _source_info = self._source_info(_repos)
                    rag_context = self.rag_service.build_context(
                        rag_results,
                        source_names={
                            repo: name for repo, (name, _b) in _source_info.items()
                        },
                    )
                    rag_used = True
                    sources, sources_detail = self._build_citations(
                        rag_results, _source_info
                    )
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
                _skip_step(
                    "rag_search",
                    5,
                    {
                        "reason": (
                            "retrieval_unavailable" if kb_error else "no_documents"
                        ),
                        "query": user_query,
                    },
                )

            # 6. Сформировать prompt (разделение доверенных/недоверенных блоков)
            _start_step("prompt_build", 6)
            prompt = self.prompt_assembly.build(
                user_query=user_query,
                conversation_memory=conversation_memory,
                rag_context=rag_context if rag_context else None,
                registry_list=self.registry.render_list(),
                registry_version=self.registry.version,
            )
            # Контекст страницы кейса (вариант A аудита 03.09): в промпт идёт
            # доверенное название из реестра — сырой текст клиента не
            # пробрасывается. Дополняется после сборки, чтобы работать с любым
            # шаблоном (в т.ч. из БД).
            if page_card is not None and not self._is_personal_status_query(user_query):
                prompt += (
                    f"\n\nКОНТЕКСТ СТРАНИЦЫ (доверенная системная информация): "
                    f"пользователь открыл страницу кейса «{page_card.title}» "
                    f"(slug: {page_slug}). Ссылки вида «этот кейс», «этот проект» "
                    f"относятся к нему. Это вопрос о существующем проекте реестра, "
                    f"а не запрос о новом."
                )
                # Гейт ФОРМА ОТВЕТА (07.09): демо-маршрут подставляется в
                # промпт только при явном демо-намерении (_has_demo_intent).
                # Без гейта посторонние вопросы («Где сейчас мой заказ?»)
                # натягивались на триггер «куда пойти» и отвечались
                # маршрутом проверки демо вместо честного отказа.
                if self._has_demo_intent(user_query):
                    prompt += (
                        f"\nФОРМА ОТВЕТА (доверенная инструкция): если пользователь "
                        f"спрашивает, что проверить в демо, куда пойти или как "
                        f"посмотреть демо, отвечайте маршрутом проверки — "
                        f"нумерованными шагами по схеме «открыть → сделать → "
                        f"увидеть». Опора — документ DEMO_ROUTE этого кейса, если "
                        f"он есть в контексте БЗ; без него соберите маршрут из "
                        f"документов кейса. Шаги маршрута — только действия "
                        f"зрителя в живом демо; не включайте шаги-проверки "
                        f"внутренних механизмов (рендер Markdown, где хранится "
                        f"история диалога, стек). Не отвечайте перечнем всех "
                        f"возможностей проекта. Вопросы «как устроен кейс», «как "
                        f"он работает», «из чего состоит» — это вопросы об "
                        f"архитектуре: отвечайте на них содержательно по "
                        f"документам кейса, без нумерованного маршрута."
                    )
                prompt += (
                    f"\nОПОРА ОТВЕТА (доверенная инструкция): если в контексте "
                    f"есть документы по теме вопроса, отвечайте по ним — в том "
                    f"числе когда релевантна только их часть (отчёт об "
                    f"эксперименте, раздел документации). Отсутствие отдельной "
                    f"страницы или сводки в БЗ — не повод для отказа: "
                    f"соберите ответ из приведённых материалов кейса. Отказ "
                    f"«в базе знаний такой информации нет» — только если среди "
                    f"контекста нет ни одного документа по теме вопроса. "
                    f"Не подменяйте ответ указанием на другой документ: если "
                    f"значения или факты есть в приведённых чанках — "
                    f"формулируйте их сразу, а не «см. документ X». Если в "
                    f"репозитории несколько групп документов о разных "
                    f"подсистемах (например, оценка промптов и дообучение "
                    f"модели) — отвечайте по группе, относящейся к теме "
                    f"страницы кейса; документы других подсистем не являются "
                    f"источником ответа о результатах этого кейса. При этом "
                    f"ни в каком виде не выдумывайте конкретные значения: "
                    f"если нужных чисел или фактов в приведённых чанках нет, "
                    f"так и скажите и укажите документ кейса, где они "
                    f"содержатся, — не заполняйте таблицу условными данными."
                )
            if _tr is not None:
                _tr.set("prompt", prompt)
                _tr.set("prompt_sha256", eval_trace_mod.content_sha256(prompt))
                if page_slug:
                    _tr.set("page_slug", page_slug)
                _tr.set("demo_intent", self._has_demo_intent(user_query))
                _tr.set(
                    "page_context_suppressed",
                    page_card is not None
                    and self._is_personal_status_query(user_query),
                )
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
            ttft_ms: int | None = None
            stream_emitted = False

            _start_step("llm_call", 8, {
                "provider": provider_key,
                "model": model_name,
                "query": user_query,
                "rag_used": rag_used,
            })
            try:
                provider = AIProviderFactory.create(provider_key, config=active_config)
                llm_start = time.monotonic()
                if on_token is not None:
                    parts: list[str] = []
                    stream_filter = _StreamHygieneFilter(len(sources))
                    async for delta in provider.generate_stream(
                        prompt,
                        temperature=active_config.temperature,
                        max_tokens=self._runtime_answer_max_tokens(active_config.max_tokens),
                    ):
                        ready = stream_filter.feed(delta)
                        if ttft_ms is None:
                            ttft_ms = int((time.monotonic() - start_time) * 1000)
                        stream_emitted = True
                        if ready:
                            parts.append(ready)
                            await on_token(ready)
                    tail = stream_filter.flush()
                    if tail:
                        parts.append(tail)
                        await on_token(tail)
                    answer = "".join(parts)
                else:
                    answer = await provider.generate(
                        prompt,
                        temperature=active_config.temperature,
                        max_tokens=self._runtime_answer_max_tokens(active_config.max_tokens),
                    )
                llm_latency_ms = int((time.monotonic() - llm_start) * 1000)
                _t_llm_ms.append(llm_latency_ms)
                _finish_step("llm_call", "ok", {
                    "provider": provider_key,
                    "model": model_name,
                    "latency_ms": llm_latency_ms,
                    "ttft_ms": ttft_ms,
                    "streamed": on_token is not None,
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
                if stream_emitted:
                    # Обрыв после начала потока: тихий fallback невозможен —
                    # часть ответа уже отдана зрителю (политика переключения
                    # «только до первого токена»).
                    if self.tracing_service and execution_id:
                        try:
                            self.tracing_service.finish_session(
                                execution_id, "error", {"error": error_message}
                            )
                        except Exception:
                            pass
                    raise StreamingGenerationError(error_message) from e

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
                        if on_token is not None:
                            parts: list[str] = []
                            stream_filter = _StreamHygieneFilter(len(sources))
                            async for delta in provider.generate_stream(
                                prompt,
                                temperature=fallback_config.temperature,
                                max_tokens=self._runtime_answer_max_tokens(
                                    fallback_config.max_tokens
                                ),
                            ):
                                ready = stream_filter.feed(delta)
                                if ttft_ms is None:
                                    ttft_ms = int((time.monotonic() - start_time) * 1000)
                                stream_emitted = True
                                if ready:
                                    parts.append(ready)
                                    await on_token(ready)
                            tail = stream_filter.flush()
                            if tail:
                                parts.append(tail)
                                await on_token(tail)
                            answer = "".join(parts)
                        else:
                            answer = await provider.generate(
                                prompt,
                                temperature=fallback_config.temperature,
                                max_tokens=self._runtime_answer_max_tokens(
                                    fallback_config.max_tokens
                                ),
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
                            "ttft_ms": ttft_ms,
                            "streamed": on_token is not None,
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
                        if stream_emitted:
                            # Обрыв фолбэка после начала потока: тихой
                            # подмены нет — честный обрыв канала.
                            if self.tracing_service and execution_id:
                                try:
                                    self.tracing_service.finish_session(
                                        execution_id, "error", {"error": str(fallback_error)}
                                    )
                                except Exception:
                                    pass
                            raise StreamingGenerationError(str(fallback_error)) from fallback_error
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

            # 8b. Гигиена цитат: вырезать [N] за пределами полученных
            # источников (дефект «цитаты за пределами топ-5»). До сохранения
            # в память и трейс, чтобы все последующие отображения ответа
            # (UI, логи, память) видели уже очищенный текст.
            answer, citations_stripped = self._strip_stale_citations(answer, len(sources))

            # 8b'. Гигиена ограждений: markdown-таблица в ```python``` рендерится
            # кодом (кейс 06.09.2026) — метка срезается до кеша/памяти/трейса.
            answer = self._normalize_table_fences(answer)

            # 8b''. Гигиена markdown-разметки: парные звёздочки и «#»-заголовки
            # срезаются до кеша/памяти/трейса (замечание приёмки 04.09.2026).
            answer = self._strip_markdown_emphasis(answer)

            # 8c. Подавление источников при честном отказе (решение владельца
            # 04.09.2026): источники собираются из retrieval-выдачи до
            # генерации и не различают отказ — панель источников под ответом
            # «такой информации нет» вводит в заблуждение: документы ничего
            # не подтвердили. Отказ отдаётся без источников и их detail
            # (панель документа в UI не показывается). Кеш не затрагивается:
            # отказы не кешируются по политике cache-eligible.
            refusal_sources_suppressed = bool(answer) and self._is_refusal(answer)
            if refusal_sources_suppressed:
                sources = []
                sources_detail = []
                if _tr is not None:
                    _tr.set("refusal_sources_suppressed", True)

            # 9. Кеш (только для ответов без истории).
            # Политика кеширования возвращена (решение владельца 04.09.2026,
            # закрытие долговой строки §8 «кеширование вернётся с признаком
            # cache-eligible»; расширение решением владельца 04.09 — без
            # требования цитаты [N]: после перехода на панель документа
            # большинство прод-ответов цитат не содержит, условие дало бы
            # малое покрытие кеша). Кешируется любой grounded-ответ, у
            # которого одновременно: rag_used (построен на найденных
            # документах), нет канонического отказа, генерация успешна у
            # основного провайдера. Парафраз отказа в нестандартной
            # формулировке может попасть в кеш (осознанный риск вместо
            # FN-эвристики §3); stale-кеш исключён fingerprint-инвалидацией
            # при смене промпта/модели/KB. Детерминированные ответы реестра
            # (листинг/счёт) кешируются как раньше в своём блоке
            # (fingerprint registry-версии, ранний return).
            cache_eligible = (
                not history_present
                and rag_used
                and not fallback_used
                and bool(answer)
                and not self._is_refusal(answer)
            )
            if cache_eligible:
                self.cache.set(
                    query=user_query,
                    response=answer,
                    metadata={
                        "provider": provider_used,
                        "model": model_used,
                        "sources": sources,
                    },
                    ttl_seconds=self.cache_ttl_seconds,
                    fingerprint=config_fingerprint,
                )
            if _tr is not None:
                _tr.set("cache_eligible", cache_eligible)
            _start_step("memory_save", 9)

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
                "citations_stripped": citations_stripped,
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
                "ttft_ms": ttft_ms,
                "rag_used": rag_used,
                "sources": sources,
                "fallback_used": fallback_used,
                "citations_stripped": citations_stripped,
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
                        "ttft_ms": ttft_ms,
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
                _tr.set("citations_stripped", citations_stripped)
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
                    "ttft_ms": ttft_ms,
                    "streamed": on_token is not None,
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