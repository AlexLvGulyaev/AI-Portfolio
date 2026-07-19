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

    @classmethod
    def from_settings(cls) -> "RAGConfig":
        """Build config from application settings (env vars)."""
        from app.core.config import get_settings

        settings = get_settings()
        return cls(
            collection_name="ai_portfolio_knowledge",
            persist_directory="data/chroma_db",
            embedding_model="text-embedding-3-small",
            chroma_use_http=settings.chroma_use_http,
            chroma_host=settings.chroma_host,
            chroma_port=settings.chroma_port,
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

    def _get_or_create_collection(self):
        """
        Получает или создаёт коллекцию.

        Источник: Assistant Flow _get_or_create_collection()
        """
        try:
            return self._client.get_collection(self.config.collection_name)
        except Exception:
            return self._client.create_collection(
                name=self.config.collection_name,
                metadata={"description": "AI Portfolio Knowledge Base"},
            )

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

        # Выполняем поиск
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self._collection.count()),
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
                ))

        return formatted_results

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

        if not results:
            return ""

        context_parts: list[str] = []
        current_length = 0

        for i, result in enumerate(results, 1):
            part = f"\n[{i}] {result.source}:\n{result.content}\n"

            if max_tokens:
                # Приблизительно 4 символа на токен
                part_tokens = len(part) // 4
                if current_length + part_tokens > max_tokens:
                    break
                current_length += part_tokens

            context_parts.append(part)

        return "".join(context_parts)

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

        self._collection = self._client.create_collection(
            name=self.config.collection_name,
            metadata={"description": "AI Portfolio Knowledge Base"},
        )

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