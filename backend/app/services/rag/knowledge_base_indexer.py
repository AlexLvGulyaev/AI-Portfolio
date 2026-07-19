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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.services.rag.rag_service import RAGConfig, RAGService


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
    Сервис индексации базы знаний в ChromaDB.

    Функции:
    - загрузка JSON-документов;
    - чанкинг документов;
    - построение embeddings;
    - запись в ChromaDB;
    - переиндексация;
    - удаление документов.

    Источник: PEcf09 (EmbeddingStore, чанкинг, эмбеддинги)
    """

    def __init__(
        self,
        rag_service: RAGService,
        knowledge_base_path: str = "knowledge_base",
    ):
        """
        Инициализация индексатора.

        Args:
            rag_service: RAG-сервис для работы с ChromaDB
            knowledge_base_path: Путь к JSON-файлам базы знаний
        """
        self.rag_service = rag_service
        self.knowledge_base_path = Path(knowledge_base_path)

    def _create_chunks(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[str]:
        """
        Разбивает текст на чанки с перекрытием.

        Источник: PEcf09 _create_chunks()

        Args:
            text: Исходный текст
            chunk_size: Размер чанка в символах
            overlap: Размер перекрытия между чанками

        Returns:
            Список чанков
        """
        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start = end - overlap

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
        """Удаляет все чанки документа из коллекции перед переиндексацией."""
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

        # Создаём эмбеддинги
        embeddings = self.rag_service._create_embeddings(chunks)

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
                "chunk_length": len(chunk),
                **document.metadata,
            })

            if document.url:
                metadata["url"] = document.url

            metadatas.append(metadata)
            ids.append(chunk_id)

        # Добавляем в коллекцию
        self.rag_service._collection.add(
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

        # Очищаем коллекцию, если требуется
        if clear_existing:
            self.rag_service.clear_collection()

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

        # Очищаем коллекцию, если требуется
        if clear_existing:
            self.rag_service.clear_collection()

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
            # Получаем все чанки документа
            results = self.rag_service._collection.get(
                where={"document_id": document_id},
            )

            ids = results.get("ids", [])
            if ids:
                self.rag_service._collection.delete(ids=ids)

            return len(ids)

        except Exception:
            return 0

    def get_document_count(self) -> dict[str, int]:
        """
        Возвращает статистику по документам.

        Returns:
            Словарь с количеством документов по категориям
        """
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