"""
Индексатор базы знаний для AI Portfolio.

Функции:
- загрузка JSON-документов;
- построение embeddings;
- запись в ChromaDB;
- переиндексация.

Источники:
- PEcf09: embeddings.py (чанкинг, эмбеддинги)
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from app.services.rag.rag_service import RAGConfig, RAGService


class IndexStore(Protocol):
    """Minimal write contract for the KB indexer's target index.

    KB indexing follows the effective-active retrieval backend (owner
    decision 29.08.2026): the store is resolved from the backend returned
    by ``retrieval_manager.get_backend()``, not hardwired to Chroma.
    """

    backend_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for chunks."""
        ...

    def delete_document_chunks(self, document_id: str) -> int:
        """Delete all chunks of a document before re-indexing it."""
        ...

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert pre-embedded chunks."""
        ...

    def clear_by_source_type(self, source_type: str) -> int:
        """Delete all chunks of a source type. Returns deleted count."""
        ...

    def clear_collection(self) -> None:
        """Delete every chunk of the index."""
        ...

    def all_document_ids(self) -> set[str]:
        """Distinct document_ids currently in the store (post-sync verify)."""
        ...


class ChromaIndexStore:
    """Chroma-backed IndexStore — delegates to the legacy RAGService methods."""

    backend_name = "chroma"

    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.rag_service._create_embeddings(texts)

    def delete_document_chunks(self, document_id: str) -> int:
        try:
            results = self.rag_service._collection.get(
                where={"document_id": document_id},
                include=[],
            )
            ids = results.get("ids", [])
            if ids:
                self.rag_service._collection.delete(ids=ids)
            return len(ids)
        except Exception:
            return 0

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.rag_service._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def clear_by_source_type(self, source_type: str) -> int:
        return self.rag_service.clear_by_source_type(source_type)

    def clear_collection(self) -> None:
        self.rag_service.clear_collection()

    def all_document_ids(self) -> set[str]:
        try:
            results = self.rag_service._collection.get(include=["metadatas"])
            return {
                str(m.get("document_id"))
                for m in (results.get("metadatas") or [])
                if isinstance(m, dict) and m.get("document_id")
            }
        except Exception:
            return set()


class WeaviateIndexStore:
    """Weaviate-backed IndexStore — delegates to WeaviateBackend write methods."""

    backend_name = "weaviate"

    def __init__(self, backend: Any):
        self._backend = backend

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._backend._embeddings_fn(texts)

    def delete_document_chunks(self, document_id: str) -> int:
        return self._backend.delete_document_chunks(document_id)

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._backend.add_chunks(ids, documents, embeddings, metadatas)

    def clear_by_source_type(self, source_type: str) -> int:
        return self._backend.clear_by_source_type(source_type)

    def clear_collection(self) -> None:
        self._backend.clear_collection()

    def all_document_ids(self) -> set[str]:
        coll = self._backend._collection()
        ids: set[str] = set()
        after: str | None = None
        # QUERY_MAXIMUM_RESULTS caps a single fetch (10000 here) — paginate
        # by after-cursor instead of raising the limit.
        while True:
            resp = coll.query.fetch_objects(
                limit=500, after=after, return_properties=["document_id"]
            )
            objs = getattr(resp, "objects", None) or []
            for obj in objs:
                doc_id = (obj.properties or {}).get("document_id")
                if doc_id:
                    ids.add(str(doc_id))
            if len(objs) < 500:
                break
            after = getattr(objs[-1], "uuid", None)
            if after is None:
                break
        return ids


def index_store_for(backend: Any) -> IndexStore:
    """Resolve the IndexStore for a (base, unwrapped) retrieval backend.

    Chroma keeps two forms: legacy RAGService (search-only surface: no
    add_chunks/delete_document_chunks) and any backend already exposing the
    write contract. RAGService is wrapped into ChromaIndexStore, which
    drives the collection through RAGService methods (sync code then
    re-wraps with a fresh RAGService built from effective tuning).
    """
    name = str(getattr(backend, "backend_name", "") or "")
    if not hasattr(backend, "add_chunks"):
        if isinstance(backend, RAGService):
            return ChromaIndexStore(backend)
        raise ValueError(
            f"backend '{name or type(backend).__name__}' does not support "
            "KB indexing (no index_store write contract)"
        )
    if name == "weaviate":
        return WeaviateIndexStore(backend)
    return ChromaIndexStore(backend)


@dataclass
class KnowledgeDocument:
    """Документ базы знаний."""

    id: str
    title: str
    content: str
    category: str = "general"
    url: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class IndexerStats:
    """Статистика индексации."""

    documents_processed: int = 0
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class KnowledgeBaseIndexer:
    """
    Сервис индексации базы знаний (запись через IndexStore).

    Функции:
    - загрузка JSON-документов;
    - чанкинг документов;
    - построение embeddings;
    - запись в индекс активного retrieval-бэкенда (Chroma | Weaviate);
    - переиндексация;
    - удаление документов.

    Источник: PEcf09 (EmbeddingStore, чанкинг, эмбеддинги)
    """

    def __init__(
        self,
        rag_service: RAGService | None = None,
        knowledge_base_path: str = "knowledge_base",
        store: IndexStore | None = None,
    ):
        """
        Инициализация индексатора.

        Args:
            rag_service: RAG-сервис для работы с ChromaDB (legacy-путь;
                формирует ChromaIndexStore, если store не передан)
            knowledge_base_path: Путь к JSON-файлам базы знаний
            store: Целевое хранилище IndexStore; KB indexing следует за
                effective-активным retrieval-бэкендом (владелец, 29.08.2026)
        """
        self.rag_service = rag_service
        if store is not None:
            self.store = store
        elif rag_service is not None:
            self.store = ChromaIndexStore(rag_service)
        else:
            raise ValueError("KnowledgeBaseIndexer requires a store or rag_service")
        self.knowledge_base_path = Path(knowledge_base_path)

    # Строка-заголовок в тексте документа (конвертер md→plain сохраняет
    # уровни: "## n8n"). Заголовки — semantic-границы для чанкования.
    _HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE)

    def _create_chunks(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[str]:
        """
        Разбивает текст на чанки: сначала по заголовкам, затем окном.

        Заголовок открывает semantic-секцию и сам несёт смысл запроса
        («## n8n» vs «Что такое n8n?»). Окно фиксированной длины режет
        секцию посередине и разбавляет её соседними блоками: узкая секция
        FAQ «Как связаться?» (4 строки, cosine 0.65 изолированно) внутри
        900-символьного чанка опускается до 0.33 и проигрывает топ-6 чата
        (решение владельца 30.08.2026: документы-источники — SOT, чанкование
        устранить). Поэтому:

        - секция целиком помещается в chunk_size → её собственный чанк
          (склейки двух секций нет — разбавление вернулось бы);
        - секция-переросток → скользящее окно c overlap, как раньше;
        - заголовков нет (JSON/прочие не-markdown документы) → прежнее
          поведение окна без изменений.

        Источник: PEcf09 _create_chunks() (окно)

        Args:
            text: Исходный текст
            chunk_size: Размер чанка в символах
            overlap: Размер перекрытия между чанками (для секций-переростков)

        Returns:
            Список чанков
        """
        boundaries = [m.start() for m in self._HEADING_RE.finditer(text)]
        # Текст до первого заголовка — шапка/интро; без заголовков в тексте
        # boundaries пуст и ниже остаётся один блок = прежнее окно.
        starts = boundaries if boundaries else [0]

        chunks: list[str] = []
        for i, sec_start in enumerate(starts):
            sec_end = (
                starts[i + 1]
                if i + 1 < len(starts)
                else len(text)
            )
            section = text[sec_start:sec_end].strip()
            if not section:
                continue

            if len(section) <= chunk_size:
                chunks.append(section)
                continue

            # Секция больше окна: скользящее окно с перекрытием.
            pos = 0
            while pos < len(section):
                piece = section[pos : pos + chunk_size].strip()
                if piece:
                    chunks.append(piece)
                if pos + chunk_size >= len(section):
                    break
                pos += chunk_size - overlap

        return chunks

    def _flatten_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Преобразует метаданные в формат, совместимый с ChromaDB.

        ChromaDB поддерживает только str, int, float, bool.

        Источник: Assistant Flow _flatten_metadata()

        Args:
            metadata: Исходные метаданные

        Returns:
            Преобразованные метаданные
        """
        result: dict[str, Any] = {}

        for key, value in metadata.items():
            if value is None:
                continue

            if isinstance(value, (str, int, float, bool)):
                result[key] = value
            else:
                result[key] = str(value)

        return result

    def _delete_document_chunks(self, document_id: str) -> int:
        """Удаляет все чанки документа из индекса перед переиндексацией."""
        return self.store.delete_document_chunks(document_id)

    def load_json_documents(self, file_path: Path) -> list[KnowledgeDocument]:
        """
        Загружает документы из JSON-файла.

        Поддерживаемые форматы JSON:

        Формат 1: Список документов
        [
            {
                "id": "doc1",
                "title": "Документ 1",
                "content": "Текст документа",
                "category": "cases",
                "url": "https://..."
            }
        ]

        Формат 2: Объект с разделами
        {
            "cases": [...],
            "services": [...],
            "technologies": [...]
        }

        Args:
            file_path: Путь к JSON-файлу

        Returns:
            Список документов
        """
        documents: list[KnowledgeDocument] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Формат 1: Список документов
            if isinstance(data, list):
                for item in data:
                    doc = KnowledgeDocument(
                        id=item.get("id", str(uuid.uuid4())),
                        title=item.get("title", "Untitled"),
                        content=item.get("content", ""),
                        category=item.get("category", "general"),
                        url=item.get("url"),
                        metadata=item.get("metadata", {}),
                    )
                    if doc.content:
                        documents.append(doc)

            # Формат 2: Объект с разделами
            elif isinstance(data, dict):
                for category, items in data.items():
                    if not isinstance(items, list):
                        continue

                    for item in items:
                        doc = KnowledgeDocument(
                            id=item.get("id", str(uuid.uuid4())),
                            title=item.get("title", "Untitled"),
                            content=item.get("content", item.get("description", "")),
                            category=category,
                            url=item.get("url"),
                            metadata=item.get("metadata", {}),
                        )
                        if doc.content:
                            documents.append(doc)

        except Exception as e:
            raise ValueError(f"Ошибка загрузки {file_path}: {e}") from e

        return documents

    def index_document(
        self,
        document: KnowledgeDocument,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> int:
        """
        Индексирует один документ в ChromaDB.

        Args:
            document: Документ для индексации
            chunk_size: Размер чанка (переопределяет конфиг)
            chunk_overlap: Размер перекрытия (переопределяет конфиг)

        Returns:
            Количество созданных чанков
        """
        chunk_size = chunk_size or self.rag_service.config.chunk_size
        chunk_overlap = chunk_overlap or self.rag_service.config.chunk_overlap

        # Удаляем предыдущие чанки документа, чтобы избежать дублирования
        # при повторной индексации.
        self._delete_document_chunks(document.id)

        # Разбиваем документ на чанки
        chunks = self._create_chunks(
            document.content,
            chunk_size=chunk_size,
            overlap=chunk_overlap,
        )

        if not chunks:
            return 0

        # Создаём эмбеддинги (бэкенд-функция эффективного бэкенда)
        embeddings = self.store.embed(chunks)

        # Формируем метаданные для каждого чанка
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{document.id}_chunk_{i}"
            metadata = self._flatten_metadata({
                "source": document.title,
                "document_id": document.id,
                "category": document.category,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk),
                **document.metadata,
            })

            if document.url:
                metadata["url"] = document.url

            metadatas.append(metadata)
            ids.append(chunk_id)

        # Добавляем в индекс активного бэкенда
        self.store.add_chunks(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return len(chunks)

    def index_documents(
        self,
        documents: list[KnowledgeDocument],
        clear_existing: bool = False,
    ) -> IndexerStats:
        """
        Индексирует список документов.

        Args:
            documents: Список документов
            clear_existing: Очистить существующую коллекцию перед индексацией

        Returns:
            Статистика индексации
        """
        import time

        stats = IndexerStats()
        start_time = time.time()

        # Очищаем индекс, если требуется
        if clear_existing:
            self.store.clear_collection()

        # Индексируем каждый документ
        for doc in documents:
            try:
                chunks_created = self.index_document(doc)
                stats.documents_processed += 1
                stats.chunks_created += chunks_created
            except Exception as e:
                error_msg = f"Document {doc.id}: {str(e)}"
                stats.errors.append(error_msg)

        stats.duration_seconds = time.time() - start_time

        return stats

    def index_json_file(
        self,
        file_path: Path,
        clear_existing: bool = False,
    ) -> IndexerStats:
        """
        Индексирует JSON-файл.

        Args:
            file_path: Путь к JSON-файлу
            clear_existing: Очистить существующую коллекцию

        Returns:
            Статистика индексации
        """
        documents = self.load_json_documents(file_path)
        return self.index_documents(documents, clear_existing=clear_existing)

    def index_directory(
        self,
        clear_existing: bool = True,
    ) -> IndexerStats:
        """
        Индексирует все JSON-файлы в директории базы знаний.

        Args:
            clear_existing: Очистить существующую коллекцию

        Returns:
            Статистика индексации
        """
        import time

        stats = IndexerStats()
        start_time = time.time()

        # Очищаем индекс, если требуется
        if clear_existing:
            self.store.clear_collection()

        # Находим все JSON-файлы
        if not self.knowledge_base_path.exists():
            return stats

        json_files = list(self.knowledge_base_path.glob("**/*.json"))

        # Индексируем каждый файл
        for json_file in json_files:
            try:
                file_stats = self.index_json_file(
                    json_file,
                    clear_existing=False,  # Не очищаем для каждого файла
                )
                stats.documents_processed += file_stats.documents_processed
                stats.chunks_created += file_stats.chunks_created
                stats.errors.extend(file_stats.errors)
            except Exception as e:
                error_msg = f"File {json_file}: {str(e)}"
                stats.errors.append(error_msg)

        stats.duration_seconds = time.time() - start_time

        return stats

    def delete_document(self, document_id: str) -> int:
        """
        Удаляет документ из индекса.

        Удаляет все чанки документа.

        Args:
            document_id: ID документа

        Returns:
            Количество удалённых чанков
        """
        try:
            return self.store.delete_document_chunks(document_id)
        except Exception:
            return 0

    def get_document_count(self) -> dict[str, int]:
        """
        Возвращает статистику по документам.

        Returns:
            Словарь с количеством документов по категориям
        """
        if self.rag_service is None:
            # Не-chroma store: сводки по категориям из индексатора не отдаём.
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "by_category": {},
            }
        try:
            # Получаем все чанки
            results = self.rag_service._collection.get(
                include=["metadatas"],
            )

            # Группируем по document_id
            document_ids: set[str] = set()
            category_counts: dict[str, int] = {}

            for metadata in (results.get("metadatas") or []):
                if isinstance(metadata, dict):
                    doc_id = metadata.get("document_id")
                    if doc_id:
                        document_ids.add(doc_id)

                    category = metadata.get("category", "general")
                    category_counts[category] = category_counts.get(category, 0) + 1

            return {
                "total_documents": len(document_ids),
                "total_chunks": self.rag_service.count_documents(),
                "by_category": category_counts,
            }

        except Exception:
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "by_category": {},
            }