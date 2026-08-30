"""
RAG-сервис для AI Portfolio.

Функции:
- подключение к ChromaDB;
- поиск документов;
- возврат найденного контекста;
- единый интерфейс сервиса.

Источники:
- PEcf09: embeddings.py (EmbeddingStore)
- Assistant Flow: rag_chroma_store.py (ChromaRagStore)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings
from openai import OpenAI


@dataclass
class SearchResult:
    """Результат поиска документа."""

    content: str
    source: str
    score: float
    metadata: dict[str, Any]
    # Additive provenance field (diagnostics/eval): ChromaDB chunk id.
    # Never returned to the user; default keeps existing call sites stable.
    chunk_id: Optional[str] = None


# Аппроксимированный HNSW-поиск Chroma на малом n_results теряет истинных
# ближайших соседей (обнаружено live 29.08.2026: топ-1 чанк с дистанцией
# 1.166 отсутствовал в выдаче при n_results=3/6/10, при 15 — ранг 1).
# Запрос выполняется с запасом, вызывающему отдаётся запрошенный top_k.
RECALL_MARGIN = 3


@dataclass
class RAGConfig:
    """Конфигурация RAG-сервиса."""

    collection_name: str = "ai_portfolio_knowledge"
    persist_directory: str = "data/chroma_db"
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 500
    chunk_overlap: int = 50
    chroma_use_http: bool = False
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    # Tunable via the retrieval console (PG overrides over env defaults):
    recall_margin: int = RECALL_MARGIN  # query oversample window (runtime tuning)
    max_distance: float = 10.0  # drop results with score above (runtime tuning)
    ef_search: int = 100  # HNSW graph search depth at collection creation (build-time)
    ef_construction: int = 100
    # OpenAI embeddings client timeout in seconds (runtime tuning, AF WH-2);
    # None keeps the SDK default.
    embedding_request_timeout: float | None = None

    @classmethod
    def from_settings(cls) -> "RAGConfig":
        """Build config from application settings (env vars)."""
        from app.core.config import get_settings

        settings = get_settings()
        return cls(
            collection_name=settings.chroma_collection_name,
            persist_directory="data/chroma_db",
            embedding_model="text-embedding-3-small",
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            chroma_use_http=settings.chroma_use_http,
            chroma_host=settings.chroma_host,
            chroma_port=settings.chroma_port,
            recall_margin=settings.retrieval_recall_margin,
            max_distance=settings.rag_max_distance,
            ef_search=settings.chroma_ef_search,
            ef_construction=settings.chroma_ef_construction,
            embedding_request_timeout=settings.rag_embedding_request_timeout,
        )


class RAGService:
    """
    Сервис работы с базой знаний через ChromaDB.

    Функции:
    - подключение к ChromaDB (HTTP или Persistent);
    - поиск документов по запросу;
    - возврат найденного контекста;
    - информация о коллекции.

    Источники:
    - PEcf09: EmbeddingStore (эмбеддинги, чанкинг, поиск)
    - Assistant Flow: ChromaRagStore (dual-mode: HTTP/Persistent)
    """

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        api_key: Optional[str] = None,
    ):
        """
        Инициализация RAG-сервиса.

        Args:
            config: Конфигурация RAG
            api_key: API ключ OpenAI (если None, берётся из переменной окружения OPENAI_API_KEY)
        """
        import os

        self.config = config or RAGConfig()
        # Если api_key не передан, берём из переменной окружения
        effective_api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if self.config.embedding_request_timeout is not None:
            self._openai_client = OpenAI(
                api_key=effective_api_key,
                timeout=self.config.embedding_request_timeout,
            )
        else:
            self._openai_client = OpenAI(api_key=effective_api_key)

        # Инициализируем ChromaDB клиент
        self._client = self._create_chroma_client()
        self._collection = self._get_or_create_collection()

    def _create_chroma_client(self) -> chromadb.api.ClientAPI:
        """
        Создаёт клиент ChromaDB.

        Поддерживает два режима:
        - HTTP: для production (отдельный сервер ChromaDB)
        - Persistent: для разработки (локальное хранение)

        Источник: Assistant Flow chromadb_client_for_config()
        """
        if self.config.chroma_use_http:
            return chromadb.HttpClient(
                host=self.config.chroma_host,
                port=self.config.chroma_port,
            )

        # Persistent mode
        persist_path = Path(self.config.persist_directory)
        persist_path.mkdir(parents=True, exist_ok=True)

        return chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )

    def _creation_configuration(self) -> Optional[Any]:
        """
        Конфигурация HNSW при создании коллекции (значения — из tuning-консоли).

        chromadb 0.5.23 создаёт коллекции с дефолтным ef_search=10 — узкое
        окно аппроксимированного поиска теряет истинный ближайший сосед
        (live 29.08.2026: точный топ-1 отсутствовал в выдаче даже при
        n_results=18). Значения управляются полями chroma_ef_search /
        chroma_ef_construction (ретривал-консоль, build-time). Официальный
        dict-API конфигурации применим с chromadb 1.x; на несовместимых
        версиях endpoints может отвергнуть ключ — тогда коллекция создаётся
        с дефолтами сервера.
        """
        try:
            return {
                "hnsw": {
                    "space": "l2",
                    "ef_search": self.config.ef_search,
                    "ef_construction": self.config.ef_construction,
                }
            }
        except Exception:
            return None

    def _get_or_create_collection(self):
        """
        Получает или создаёт коллекцию.

        Источник: Assistant Flow _get_or_create_collection()
        """
        try:
            return self._client.get_collection(self.config.collection_name)
        except Exception:
            create_kwargs: dict[str, Any] = {
                "name": self.config.collection_name,
                "metadata": {"description": "AI Portfolio Knowledge Base"},
            }
            configuration = self._creation_configuration()
            if configuration is not None:
                create_kwargs["configuration"] = configuration
            return self._client.create_collection(**create_kwargs)

    def _create_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Создаёт эмбеддинги для списка текстов через OpenAI API.

        Источник: PEcf09 _create_embeddings()

        Args:
            texts: Список текстов

        Returns:
            Список векторов эмбеддингов
        """
        response = self._openai_client.embeddings.create(
            model=self.config.embedding_model,
            input=texts,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]

    def search(
        self,
        query: str,
        top_k: int = 3,
        where: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        """
        Выполняет семантический поиск по базе знаний.

        Источник: PEcf09 search(), Assistant Flow native_similarity_search_with_score()

        Args:
            query: Поисковый запрос
            top_k: Количество результатов
            where: Фильтр по метаданным

        Returns:
            Список результатов поиска
        """
        if not query.strip():
            return []

        # Проверяем, есть ли документы в коллекции
        if self._collection.count() == 0:
            return []

        # Создаём эмбеддинг для запроса
        query_embeddings = self._create_embeddings([query])
        query_embedding = query_embeddings[0]

        # Выполняем поиск: с запасом против HNSW-выпадения истинного top-1,
        # вызывающему — ровно top_k (см. комментарий к RECALL_MARGIN).
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k * self.config.recall_margin, self._collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        # Форматируем результаты
        formatted_results: list[SearchResult] = []

        if results.get("documents") and len(results["documents"][0]) > 0:
            for i in range(len(results["documents"][0])):
                content = results["documents"][0][i] or ""
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                source = metadata.get("source", "unknown")

                formatted_results.append(SearchResult(
                    content=content,
                    source=source,
                    score=float(distance),
                    metadata=metadata,
                    chunk_id=results["ids"][0][i] if results.get("ids") else None,
                ))

        # rag_max_distance (runtime tuning): честный порог вместо молчаливой выдачи дальнего.
        return [r for r in formatted_results if r.score <= self.config.max_distance][: top_k]

    def get_context(
        self,
        query: str,
        top_k: int = 3,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Возвращает контекст для LLM в виде строки.

        Форматирует результаты поиска в строку для использования в промпте.

        Args:
            query: Поисковый запрос
            top_k: Количество результатов
            max_tokens: Максимальное количество токенов (приблизительно)

        Returns:
            Строка с контекстом
        """
        results = self.search(query, top_k=top_k)
        return self.build_context(results, max_tokens=max_tokens)

    def build_context(
        self,
        results: list[SearchResult],
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Строит контекст из УЖЕ полученных результатов поиска (без повторного
        search — устраняет двойной retrieval).

        Args:
            results: Результаты search()
            max_tokens: Максимальное количество токенов (приблизительно)

        Returns:
            Строка с контекстом (пустая, если результатов нет)
        """
        if not results:
            return ""

        context_parts: list[str] = []
        current_length = 0

        for i, result in enumerate(results, 1):
            # Понятная пользователю/модели метка источника: репозиторий · путь
            repo = result.metadata.get("repo")
            label = f"{repo} · {result.source}" if repo else result.source
            part = f"\n[{i}] {label}:\n{result.content}\n"

            if max_tokens:
                # Приблизительно 4 символа на токен
                part_tokens = len(part) // 4
                if current_length + part_tokens > max_tokens:
                    break
                current_length += part_tokens

            context_parts.append(part)

        return "".join(context_parts)

    def search_diverse(
        self,
        query: str,
        repos: list[str],
        per_repo_k: int = 1,
        final_top_k: int = 6,
        max_per_repo: int = 2,
    ) -> list[SearchResult]:
        """
        Поиск с диверсификацией по репозиториям для межпроектных запросов.

        Один embedding-вызов на запрос; по одному Chroma-запросу на репозиторий
        (ограниченный fan-out). Один репозиторий не может занять весь контекст.

        Args:
            query: Поисковый запрос
            repos: Список репозиториев (metadata.repo в коллекции)
            per_repo_k: Сколько ближайших чанков брать из каждого репозитория
            final_top_k: Итоговое число чанков после слияния
            max_per_repo: Максимум чанков одного репозитория в итоговой выдаче

        Returns:
            Список SearchResult, отсортированный по дистанции
        """
        if not query.strip() or not repos or self._collection.count() == 0:
            return []

        query_embedding = self._create_embeddings([query])[0]

        merged: list[SearchResult] = []
        for repo in repos:
            try:
                results = self._collection.query(
                    query_embeddings=[query_embedding],
                    # С запасом против HNSW-выпадения (см. RECALL_MARGIN);
                    # квоты max_per_repo/final_top_k отсекают лишнее ниже.
                    n_results=min(per_repo_k * self.config.recall_margin, self._collection.count()),
                    include=["documents", "metadatas", "distances"],
                    where={"repo": {"$eq": repo}},
                )
            except Exception:
                continue
            if not (results.get("documents") and results["documents"][0]):
                continue
            for i in range(len(results["documents"][0])):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                merged.append(SearchResult(
                    content=results["documents"][0][i] or "",
                    source=metadata.get("source", "unknown"),
                    score=float(results["distances"][0][i] if results.get("distances") else 0.0),
                    metadata=metadata,
                    chunk_id=results["ids"][0][i] if results.get("ids") else None,
                ))

        # Слияние по дистанции с квотой на репозиторий.
        merged.sort(key=lambda r: r.score)
        repo_counts: dict[str, int] = {}
        diversified: list[SearchResult] = []
        for r in merged:
            repo = r.metadata.get("repo") or "?"
            if repo_counts.get(repo, 0) >= max_per_repo:
                continue
            repo_counts[repo] = repo_counts.get(repo, 0) + 1
            diversified.append(r)
            if len(diversified) >= final_top_k:
                break
        return diversified

    def get_collection_info(self) -> dict[str, Any]:
        """
        Возвращает информацию о коллекции.

        Returns:
            Словарь с информацией
        """
        return {
            "name": self.config.collection_name,
            "count": self._collection.count(),
            "embedding_model": self.config.embedding_model,
            "persist_directory": self.config.persist_directory,
        }

    def count_documents(self) -> int:
        """
        Возвращает количество документов в коллекции.

        Returns:
            Количество документов
        """
        return self._collection.count()

    def clear_collection(self) -> None:
        """
        Очищает коллекцию.

        Удаляет коллекцию и создаёт заново.
        """
        try:
            self._client.delete_collection(self.config.collection_name)
        except Exception:
            pass

        create_kwargs: dict[str, Any] = {
            "name": self.config.collection_name,
            "metadata": {"description": "AI Portfolio Knowledge Base"},
        }
        configuration = self._creation_configuration()
        if configuration is not None:
            create_kwargs["configuration"] = configuration
        self._collection = self._client.create_collection(**create_kwargs)

    def clear_by_source_type(self, source_type: str) -> int:
        """
        Deletes all chunks whose metadata.source_type equals the given value.

        Returns the number of deleted chunks.
        """
        deleted = 0
        try:
            while True:
                results = self._collection.get(
                    where={"source_type": source_type},
                    include=[],
                    limit=1000,
                )
                ids = results.get("ids", [])
                if not ids:
                    break
                self._collection.delete(ids=ids)
                deleted += len(ids)
                if len(ids) < 1000:
                    break
            return deleted
        except Exception:
            return deleted

    def refresh_client_and_collection(self) -> None:
        """
        Обновляет клиент и коллекцию.

        Источник: Assistant Flow refresh_client_and_collection()

        Используется после внешней переиндексации.
        """
        self._client = self._create_chroma_client()
        self._collection = self._get_or_create_collection()

    def get_chunks_by_metadata(
        self,
        where: dict[str, Any],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Возвращает чанки коллекции, соответствующие фильтру метаданных.

        Args:
            where: Фильтр по метаданным ChromaDB.
            limit: Максимальное количество чанков.

        Returns:
            Список чанков с содержимым и метаданными.
        """
        if self._collection.count() == 0:
            return []

        results = self._collection.get(
            where=where,
            limit=limit,
            include=["documents", "metadatas"],
        )

        chunks: list[dict[str, Any]] = []
        if results.get("documents") and len(results["documents"]) > 0:
            for i in range(len(results["documents"])):
                chunks.append({
                    "id": results["ids"][i] if results.get("ids") else None,
                    "content": results["documents"][i] or "",
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                })

        return chunks

    def chunk_counts_by_document(self) -> dict[str, int]:
        """Chunk count per document_id — documents console list badges.

        Chroma has no server-side group_by aggregate, so metadata is pulled
        once and counted client-side (parity with WeaviateBackend; the legacy
        chroma copy of the corpus is bounded — this only runs when chroma is
        the active backend).
        """
        if self._collection.count() == 0:
            return {}
        results = self._collection.get(include=["metadatas"], limit=100000)
        counts: dict[str, int] = {}
        for meta in results.get("metadatas") or []:
            doc_id = (meta or {}).get("document_id") if isinstance(meta, dict) else None
            if doc_id:
                counts[str(doc_id)] = counts.get(str(doc_id), 0) + 1
        return counts

    def list_document_chunks(
        self, document_id: str, limit: int = 2000
    ) -> list[dict[str, Any]]:
        """All chunks of a document ordered by chunk_index (documents console).

        Same response shape as WeaviateBackend.list_document_chunks.
        """
        if self._collection.count() == 0:
            return []
        results = self._collection.get(
            where={"document_id": {"$eq": document_id}},
            limit=max(1, int(limit)),
            include=["documents", "metadatas"],
        )
        chunks: list[dict[str, Any]] = []
        if results.get("documents") and len(results["documents"]) > 0:
            for i in range(len(results["documents"])):
                chunks.append({
                    "id": results["ids"][i] if results.get("ids") else None,
                    "content": results["documents"][i] or "",
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                })
        chunks.sort(key=lambda c: (c["metadata"].get("chunk_index") is None,
                                   c["metadata"].get("chunk_index") or 0))
        return chunks

    def count_document_chunks(self, document_id: str) -> int:
        """Chunk count for one document (light: ids only, no content)."""
        if self._collection.count() == 0:
            return 0
        try:
            results = self._collection.get(
                where={"document_id": {"$eq": document_id}},
                include=[],
                limit=100000,
            )
        except Exception:
            return 0
        return len(results.get("ids") or [])