#!/usr/bin/env python3
"""
Smoke-тесты для Этапа 2.2 сервисного слоя.

Проверяют:
1. Response Cache — кеширование ответов
2. RAG Service — поиск документов
3. Knowledge Base Indexer — индексация базы знаний
4. Интеграция сервисов — совместная работа
"""

import json
import os
import sys
import time
from pathlib import Path

# Добавляем путь к модулям backend
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.config import get_settings
from app.services.cache.response_cache import ResponseCache
from app.services.rag.rag_service import RAGConfig, RAGService
from app.services.rag.knowledge_base_indexer import KnowledgeBaseIndexer, KnowledgeDocument


def test_response_cache():
    """Тестирует Response Cache."""
    print("\n" + "=" * 60)
    print("Testing Response Cache...")
    print("=" * 60)

    # Используем временный файл для теста
    cache_file = backend_path / "data" / "cache" / "test_cache.json"

    # Создаём кеш
    cache = ResponseCache(
        cache_file=str(cache_file),
        ttl_seconds=3600,  # 1 час
        enable_persistence=True,
    )

    # Тест 1: Проверяем пустой кеш
    print("\n[1] Testing empty cache...")
    result = cache.get("test query")
    assert result is None, "Expected None for empty cache"
    print("✓ Empty cache returns None")

    # Тест 2: Сохраняем ответ
    print("\n[2] Testing set...")
    cache.set(
        query="What services do you offer?",
        response="I offer AI automation services...",
        metadata={"model": "gpt-4.1-mini", "provider": "openai"},
    )
    print("✓ Response saved to cache")

    # Тест 3: Получаем ответ из кеша
    print("\n[3] Testing get (hit)...")
    result = cache.get("What services do you offer?")
    assert result is not None, "Expected cached response"
    assert "AI automation" in result, "Expected 'AI automation' in response"
    print(f"✓ Cache hit: {result[:50]}...")

    # Тест 4: Проверяем статистику
    print("\n[4] Testing stats...")
    stats = cache.get_stats()
    assert stats.total_sets == 1, "Expected 1 set"
    assert stats.total_hits == 1, "Expected 1 hit"
    print(f"✓ Stats: sets={stats.total_sets}, hits={stats.total_hits}, misses={stats.total_misses}")

    # Тест 5: Получаем полную запись
    print("\n[5] Testing get_entry...")
    entry = cache.get_entry("What services do you offer?")
    assert entry is not None, "Expected cache entry"
    assert entry.metadata.get("model") == "gpt-4.1-mini", "Expected model metadata"
    assert entry.metadata.get("provider") == "openai", "Expected provider metadata"
    print(f"✓ Entry metadata: model={entry.metadata.get('model')}, provider={entry.metadata.get('provider')}")

    # Тест 6: Инвалидизация
    print("\n[6] Testing invalidate...")
    invalidated = cache.invalidate("What services do you offer?")
    assert invalidated is True, "Expected invalidation to succeed"
    result = cache.get("What services do you offer?")
    assert result is None, "Expected None after invalidation"
    print("✓ Entry invalidated successfully")

    # Тест 7: TTL
    print("\n[7] Testing TTL...")
    cache.set("test ttl", "test response", ttl_seconds=1)  # 1 секунда
    result = cache.get("test ttl")
    assert result is not None, "Expected cached response"
    print("✓ Entry cached with TTL")
    time.sleep(2)  # Ждём истечения TTL
    result = cache.get("test ttl")
    assert result is None, "Expected None after TTL expiration"
    print("✓ TTL expired as expected")

    # Тест 8: Проверка персистентности
    print("\n[8] Testing persistence...")
    cache.set("persist test", "persist value")
    cache_file_path = Path(cache_file)
    assert cache_file_path.exists(), "Expected cache file to exist"
    with open(cache_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "entries" in data, "Expected entries in cache file"
    assert "persist test" in json.dumps(data), "Expected persisted entry"
    print("✓ Cache persisted to file")

    # Очистка
    cache.invalidate_all()
    cache_file_path.unlink(missing_ok=True)

    print("\n✓ test_response_cache PASSED")
    return True


def test_rag_service():
    """Тестирует RAG Service с реальным OpenAI API."""
    print("\n" + "=" * 60)
    print("Testing RAG Service...")
    print("=" * 60)

    # Проверяем наличие API ключа
    api_key = get_settings().openai_api_key
    if not api_key:
        print("⚠ OPENAI_API_KEY not set, skipping RAG service test")
        return None

    # Конфигурация
    config = RAGConfig(
        collection_name="test_ai_portfolio_knowledge",
        persist_directory=str(backend_path / "data" / "test_chroma_db"),
        embedding_model="text-embedding-3-small",
        chroma_use_http=False,
    )

    # Создаём сервис
    rag = RAGService(config=config, api_key=api_key)

    # Тест 1: Информация о коллекции
    print("\n[1] Testing collection info...")
    info = rag.get_collection_info()
    print(f"✓ Collection: {info['name']}, count: {info['count']}")

    # Тест 2: Очищаем коллекцию
    print("\n[2] Testing clear_collection...")
    rag.clear_collection()
    count = rag.count_documents()
    assert count == 0, "Expected empty collection"
    print("✓ Collection cleared")

    # Тест 3: Добавляем тестовые документы напрямую
    print("\n[3] Testing add documents...")
    test_docs = [
        "Assistant Flow — AI-платформа для работы с документами.",
        "Review Flow — AI-сервис для обработки отзывов.",
        "AI Portfolio — публичная витрина AI-инженера.",
    ]

    # Создаём эмбеддинги
    embeddings = rag._create_embeddings(test_docs)

    # Добавляем в коллекцию
    rag._collection.add(
        ids=["test_1", "test_2", "test_3"],
        documents=test_docs,
        embeddings=embeddings,
        metadatas=[
            {"source": "test", "category": "test"},
            {"source": "test", "category": "test"},
            {"source": "test", "category": "test"},
        ],
    )

    count = rag.count_documents()
    print(f"✓ Added {count} documents to collection")

    # Тест 4: Поиск документов
    print("\n[4] Testing search...")
    results = rag.search("AI платформа", top_k=2)
    assert len(results) > 0, "Expected search results"
    print(f"✓ Found {len(results)} results")
    for i, r in enumerate(results):
        print(f"  [{i+1}] score={r.score:.4f}, source={r.source}")
        print(f"      content: {r.content[:60]}...")

    # Тест 5: Получение контекста
    print("\n[5] Testing get_context...")
    context = rag.get_context("AI платформа", top_k=2)
    assert len(context) > 0, "Expected context"
    print(f"✓ Context length: {len(context)} chars")
    print(f"  Context preview: {context[:100]}...")

    # Очистка
    print("\n[6] Cleaning up...")
    rag.clear_collection()

    # Удаляем тестовую директорию
    import shutil
    test_dir = Path(config.persist_directory)
    if test_dir.exists():
        shutil.rmtree(test_dir)

    print("✓ test_rag_service PASSED")
    return True


def test_knowledge_base_indexer():
    """Тестирует Knowledge Base Indexer."""
    print("\n" + "=" * 60)
    print("Testing Knowledge Base Indexer...")
    print("=" * 60)

    # Проверяем наличие API ключа
    api_key = get_settings().openai_api_key
    if not api_key:
        print("⚠ OPENAI_API_KEY not set, skipping indexer test")
        return None

    # Конфигурация
    config = RAGConfig(
        collection_name="test_ai_portfolio_kb",
        persist_directory=str(backend_path / "data" / "test_kb_chroma"),
        embedding_model="text-embedding-3-small",
        chunk_size=500,
        chunk_overlap=50,
    )

    rag = RAGService(config=config, api_key=api_key)
    indexer = KnowledgeBaseIndexer(
        rag_service=rag,
        knowledge_base_path=str(backend_path / "knowledge_base"),
    )

    # Тест 1: Загрузка JSON-документов
    print("\n[1] Testing load_json_documents...")
    kb_file = backend_path / "knowledge_base" / "knowledge.json"
    if not kb_file.exists():
        print("⚠ Knowledge base file not found, creating test data...")
        # Тестовые документы
        test_docs = [
            KnowledgeDocument(
                id="test_1",
                title="Test Document 1",
                content="Это тестовый документ для проверки индексации.",
                category="test",
            ),
            KnowledgeDocument(
                id="test_2",
                title="Test Document 2",
                content="Второй тестовый документ с другим содержанием.",
                category="test",
            ),
        ]
    else:
        test_docs = indexer.load_json_documents(kb_file)

    print(f"✓ Loaded {len(test_docs)} documents")
    for doc in test_docs[:3]:
        print(f"  - {doc.id}: {doc.title} ({doc.category})")

    # Тест 2: Индексация документов
    print("\n[2] Testing index_documents...")
    stats = indexer.index_documents(test_docs[:2], clear_existing=True)
    print(f"✓ Indexed {stats.documents_processed} documents")
    print(f"  Chunks created: {stats.chunks_created}")
    print(f"  Duration: {stats.duration_seconds:.2f}s")
    if stats.errors:
        print(f"  Errors: {stats.errors}")

    # Тест 3: Количество документов
    print("\n[3] Testing count_documents...")
    count = rag.count_documents()
    print(f"✓ Total chunks in collection: {count}")

    # Тест 4: Поиск по проиндексированным документам
    print("\n[4] Testing search in indexed documents...")
    results = rag.search("AI платформа", top_k=3)
    print(f"✓ Found {len(results)} results:")
    for i, r in enumerate(results):
        print(f"  [{i+1}] score={r.score:.4f}, source={r.source}")
        print(f"      content: {r.content[:80]}...")

    # Тест 5: Статистика по документам
    print("\n[5] Testing get_document_count...")
    doc_stats = indexer.get_document_count()
    print(f"✓ Documents: {doc_stats['total_documents']}")
    print(f"  Total chunks: {doc_stats['total_chunks']}")
    print(f"  By category: {doc_stats['by_category']}")

    # Тест 6: Удаление документа
    print("\n[6] Testing delete_document...")
    if test_docs:
        deleted = indexer.delete_document(test_docs[0].id)
        print(f"✓ Deleted {deleted} chunks for document {test_docs[0].id}")
        count_after = rag.count_documents()
        print(f"  Remaining chunks: {count_after}")

    # Очистка
    print("\n[7] Cleaning up...")
    rag.clear_collection()
    import shutil
    test_dir = Path(config.persist_directory)
    if test_dir.exists():
        shutil.rmtree(test_dir)

    print("✓ test_knowledge_base_indexer PASSED")
    return True


def test_services_integration():
    """Тестирует интеграцию всех сервисов."""
    print("\n" + "=" * 60)
    print("Testing Services Integration...")
    print("=" * 60)

    # Проверяем наличие API ключа
    api_key = get_settings().openai_api_key
    if not api_key:
        print("⚠ OPENAI_API_KEY not set, skipping integration test")
        return None

    # Создаём сервисы
    print("\n[1] Creating services...")

    # Response Cache
    cache = ResponseCache(
        cache_file=str(backend_path / "data" / "cache" / "integration_test_cache.json"),
        ttl_seconds=3600,
    )
    print("✓ ResponseCache created")

    # RAG Service
    config = RAGConfig(
        collection_name="test_integration",
        persist_directory=str(backend_path / "data" / "test_integration_chroma"),
    )
    rag = RAGService(config=config, api_key=api_key)
    print("✓ RAGService created")

    # Knowledge Base Indexer
    indexer = KnowledgeBaseIndexer(
        rag_service=rag,
        knowledge_base_path=str(backend_path / "knowledge_base"),
    )
    print("✓ KnowledgeBaseIndexer created")

    # Тестовый сценарий интеграции
    print("\n[2] Running integration scenario...")

    # Сценарий: Пользователь задаёт вопрос
    user_query = "Какие технологии используются в Assistant Flow?"

    # Шаг 1: Проверяем кеш
    print(f"\n  Step 1: Check cache for '{user_query}'")
    cached_response = cache.get(user_query)
    if cached_response:
        print(f"  ✓ Cache hit: {cached_response[:50]}...")
        return True
    else:
        print("  ✓ Cache miss, proceeding to RAG...")

    # Шаг 2: Индексируем документы
    print("\n  Step 2: Index knowledge base...")
    test_docs = [
        KnowledgeDocument(
            id="assistant-flow",
            title="Assistant Flow",
            content="Assistant Flow — AI-платформа для работы с документами. Технологии: Python, FastAPI, RAG, ChromaDB, PostgreSQL, Telegram Bot.",
            category="cases",
        ),
    ]
    stats = indexer.index_documents(test_docs, clear_existing=True)
    print(f"  ✓ Indexed {stats.chunks_created} chunks")

    # Шаг 3: Ищем релевантный контекст
    print(f"\n  Step 3: Search RAG for '{user_query}'...")
    results = rag.search(user_query, top_k=2)
    print(f"  ✓ Found {len(results)} results")
    for i, r in enumerate(results):
        print(f"    [{i+1}] {r.source}: {r.content[:60]}...")

    # Шаг 4: Получаем контекст
    print("\n  Step 4: Get context for LLM...")
    context = rag.get_context(user_query, top_k=2)
    print(f"  ✓ Context length: {len(context)} chars")

    # Шаг 5: Сохраняем ответ в кеш
    print("\n  Step 5: Cache the response...")
    mock_response = "Assistant Flow использует Python, FastAPI, RAG, ChromaDB, PostgreSQL и Telegram Bot."
    cache_key = cache.set(
        query=user_query,
        response=mock_response,
        metadata={
            "model": "gpt-4.1-mini",
            "provider": "openai",
            "sources": [r.source for r in results],
        },
    )
    print(f"  ✓ Cached with key: {cache_key[:16]}...")

    # Шаг 6: Проверяем кеш
    print("\n  Step 6: Verify cache...")
    cached = cache.get(user_query)
    assert cached is not None, "Expected cached response"
    assert mock_response in cached, "Expected mock response"
    print(f"  ✓ Cache verification: {cached[:50]}...")

    # Шаг 7: Проверяем метаданные
    print("\n  Step 7: Verify metadata...")
    entry = cache.get_entry(user_query)
    assert entry is not None, "Expected cache entry"
    assert entry.metadata.get("provider") == "openai", "Expected provider metadata"
    print(f"  ✓ Metadata: provider={entry.metadata.get('provider')}")

    # Шаг 8: Статистика
    print("\n  Step 8: Check statistics...")
    stats = cache.get_stats()
    print(f"  ✓ Cache stats: hits={stats.total_hits}, sets={stats.total_sets}")
    print(f"  ✓ RAG stats: documents={rag.count_documents()}")

    # Очистка
    print("\n[3] Cleaning up...")
    cache.invalidate_all()
    rag.clear_collection()
    import shutil
    test_dir = Path(config.persist_directory)
    if test_dir.exists():
        shutil.rmtree(test_dir)
    cache_file = Path(cache.cache_file)
    cache_file.unlink(missing_ok=True)

    print("✓ test_services_integration PASSED")
    return True


def main():
    """Запускает все smoke-тесты."""
    print("=" * 60)
    print("Stage 2.2 Service Layer Smoke Tests")
    print("=" * 60)

    results = []

    # Тест 1: Response Cache
    try:
        result = test_response_cache()
        results.append(("test_response_cache", result))
    except Exception as e:
        print(f"✗ test_response_cache FAILED: {e}")
        results.append(("test_response_cache", False))

    # Тест 2: RAG Service
    try:
        result = test_rag_service()
        results.append(("test_rag_service", result))
    except Exception as e:
        print(f"✗ test_rag_service FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("test_rag_service", False))

    # Тест 3: Knowledge Base Indexer
    try:
        result = test_knowledge_base_indexer()
        results.append(("test_knowledge_base_indexer", result))
    except Exception as e:
        print(f"✗ test_knowledge_base_indexer FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("test_knowledge_base_indexer", False))

    # Тест 4: Integration
    try:
        result = test_services_integration()
        results.append(("test_services_integration", result))
    except Exception as e:
        print(f"✗ test_services_integration FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(("test_services_integration", False))

    # Итоги
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    passed = sum(1 for _, r in results if r is True)
    skipped = sum(1 for _, r in results if r is None)
    failed = sum(1 for _, r in results if r is False)

    for name, result in results:
        status = "✓ PASSED" if result is True else "⚠ SKIPPED" if result is None else "✗ FAILED"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed} passed, {skipped} skipped, {failed} failed")

    if failed > 0:
        return 1

    print("\n✓ All tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())