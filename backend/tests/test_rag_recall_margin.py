"""
Unit-тесты margin-квоты retrieval (правило владельца «Решение 1», 29.08.2026).

Аппроксимированный HNSW-поиск Chroma на малом n_results теряет истинных
ближайших соседей (live-находка 29.08.2026: топ-1 чанк с дистанцией 1.166
отсутствовал в выдаче при n_results=3/6/10, при 15 — ранг 1). `search`
и `search_diverse` запрашивают n_results с запасом (RECALL_MARGIN) и
обрезают до запрошенного top_k.

RAGService не инстанцируется (коннекты к OpenAI/Chroma) — собирается через
object.__new__ с подменённой коллекцией и эмбеддингами.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag.rag_service import RAGService, RECALL_MARGIN


class FakeCollection:
    """Ловит параметры query() и возвращает заготовленный пакет результатов."""

    def __init__(self, count=100, payload=None):
        self._count = count
        self._payload = payload
        self.calls: list[dict] = []
        if payload is None:
            # Дефолт: k' чанков с дистанциями 0.5.. с запасом сверх top_k.
            self._payload = lambda k: (
                [[f"chunk-{i}" for i in range(k)]],
                [[{"repo": "o/r", "source": f"f{i}.md"} for i in range(k)]],
                [[0.5 + i / 100 for i in range(k)]],
                [[f"id-{i}" for i in range(k)]],
            )

    def count(self):
        return self._count

    def query(self, **kwargs):
        self.calls.append(kwargs)
        n = kwargs["n_results"]
        docs, metas, dists, ids = self._payload(n)
        return {
            "documents": docs,
            "metadatas": metas,
            "distances": dists,
            "ids": ids,
        }


def make_service(collection: FakeCollection, recall_margin: int = RECALL_MARGIN) -> RAGService:
    svc = object.__new__(RAGService)
    svc.config = type("C", (), {"recall_margin": recall_margin, "max_distance": 10.0})()
    svc._collection = collection
    svc._create_embeddings = lambda texts: [[0.1] * 8]
    return svc


def test_search_queries_with_margin():
    """search(top_k=6) запрашивает у Chroma top_k*3, отдаёт ровно 6."""
    col = FakeCollection(count=5620)
    res = make_service(col).search("якорная фраза", top_k=6)
    assert col.calls[0]["n_results"] == 6 * RECALL_MARGIN, col.calls
    assert len(res) == 6
    # Нормальная сортировка по дистанции сохраняется.
    assert all(a.score <= b.score for a, b in zip(res, res[1:]))
    print("PASS: search queries with margin, returns exactly top_k")


def test_search_trim_selects_best_from_margin():
    """Обрезка до top_k берёт лучшие дистанции окна, а не первые k заготовленных."""
    col = FakeCollection(count=1000, payload=lambda k: (
        [[f"chunk-{i}" for i in range(k)]],
        [[{"repo": "o/r", "source": f"f{i}.md"} for i in range(k)]],
        [[float(i) for i in range(k)]],  # дистанция == индекс
        [[f"id-{i}" for i in range(k)]],
    ))
    res = make_service(col).search("q", top_k=3)
    assert [r.score for r in res] == [0.0, 1.0, 2.0]
    assert [r.chunk_id for r in res] == ["id-0", "id-1", "id-2"]
    print("PASS: trim keeps nearest chunks from margin window")


def test_search_caps_n_results_at_collection_count():
    col = FakeCollection(count=4)
    res = make_service(col).search("q", top_k=6)
    assert col.calls[0]["n_results"] == 4
    assert len(res) == 4
    print("PASS: n_results capped by collection size")


def test_search_passes_where_and_empty_query():
    col = FakeCollection()
    make_service(col).search("q", top_k=2, where={"repo": {"$nin": ["o/hidden"]}})
    assert col.calls[0]["where"] == {"repo": {"$nin": ["o/hidden"]}}
    col2 = FakeCollection()
    assert make_service(col2).search("   ", top_k=2) == []
    assert col2.calls == []
    print("PASS: where passthrough, empty query short-circuit without query")


def test_search_diverse_queries_with_margin():
    """per_repo_k=2 → Chroma получает 2*RECALL_MARGIN на репозиторий."""
    col = FakeCollection(count=5620)

    def query(**kwargs):
        repo = kwargs["where"]["repo"]["$eq"]
        col.calls.append(kwargs)
        n = kwargs["n_results"]
        return {
            "documents": [[f"c-{i}" for i in range(n)]],
            "metadatas": [[{"repo": repo, "source": f"f{i}.md"} for i in range(n)]],
            "distances": [[0.5 + i / 10 for i in range(n)]],
            "ids": [[f"id-{i}" for i in range(n)]],
        }

    col.query = query
    res = make_service(col).search_diverse("q", repos=["o/r1", "o/r2"], per_repo_k=2)
    assert all(c["n_results"] == 2 * RECALL_MARGIN for c in col.calls), col.calls
    # Слияние по дистанции, квота и финальный top_k сохраняются.
    assert all(a.score <= b.score for a, b in zip(res, res[1:]))
    print("PASS: search_diverse queries per-repo with margin, merge/quota intact")


def test_margin_value():
    """Запас зафиксирован (улучшение заметно с 6→15, 3x даёт 18 > 15)."""
    assert RECALL_MARGIN == 3
    print("PASS: RECALL_MARGIN == 3")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL RECALL MARGIN TESTS PASSED")

# ---------- создание коллекций: ef_search=100 (решение владельца, вариант 2) ----------

class FakeChromaClient:
    """Ловит create_collection и отказывает в get_collection (ветка create)."""

    def __init__(self):
        self.created_kwargs = None

    def get_collection(self, name):
        raise Exception("not found")

    def create_collection(self, **kwargs):
        self.created_kwargs = kwargs
        return object()


def _svc_with_fake_client():
    """Экземпляр RAGService без коннектов: только клиент и get_or_create."""
    svc = object.__new__(RAGService)
    svc.config = type("C", (), {"collection_name": "t", "ef_search": 100, "ef_construction": 100})()
    svc._client = FakeChromaClient()
    svc._collection = svc._get_or_create_collection()
    return svc, svc._client


def test_creation_configuration_sets_ef_search_100():
    """Хелпер выдаёт официальный dict-API конфигурации с ef_search из конфига."""
    svc = object.__new__(RAGService)
    svc.config = type("C", (), {"ef_search": 100, "ef_construction": 100})()
    cfg = svc._creation_configuration()
    assert cfg is not None
    assert cfg == {"hnsw": {"space": "l2", "ef_search": 100, "ef_construction": 100}}
    print("PASS: creation configuration uses dict API with ef_search=100")


def test_get_or_create_passes_configuration_on_create():
    """Ветка create (коллекции нет) передаёт configuration с ef_search=100."""
    _, client = _svc_with_fake_client()
    assert client.created_kwargs is not None
    cfg = client.created_kwargs.get("configuration")
    assert cfg is not None, "configuration must be passed when creating"
    assert cfg["hnsw"]["ef_search"] == 100
    print("PASS: create path passes ef_search=100 configuration")


def test_clear_collection_creates_with_ef_search_100():
    """Пересоздание (clear_collection) также строит коллекцию с ef_search=100."""
    client = FakeChromaClient()
    svc = object.__new__(RAGService)
    svc.config = type("C", (), {"collection_name": "t", "ef_search": 100, "ef_construction": 100})()
    svc._client = client
    svc.clear_collection()
    cfg = client.created_kwargs.get("configuration")
    assert cfg is not None
    assert cfg["hnsw"]["ef_search"] == 100
    print("PASS: clear_collection recreate path uses ef_search=100")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL RECALL MARGIN TESTS PASSED")
