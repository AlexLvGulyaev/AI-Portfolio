"""KB indexing follows the active retrieval backend (owner decision
29.08.2026): index_store contract, Weaviate write half, resolution logic.

Run inside the backend container: python tests/test_indexing_active_backend.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.knowledge_base_indexer import (  # noqa: E402
    ChromaIndexStore,
    IndexStore,
    KnowledgeBaseIndexer,
    KnowledgeDocument,
    WeaviateIndexStore,
    index_store_for,
)
from app.services.rag.weaviate_backend import WeaviateBackend  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


class FakeWeaviateData:
    def __init__(self, doc_ids: set[str] | None = None) -> None:
        self.inserted: list[Any] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.insert_errors: dict[int, Any] = {}
        self.doc_ids = doc_ids or set()

    def insert_many(self, props: list[Any]) -> SimpleNamespace:
        self.inserted.extend(props)
        if self.insert_errors:
            return SimpleNamespace(successful=0, matches=0, errors=dict(self.insert_errors))
        return SimpleNamespace(successful=len(props), matches=len(props), errors={})

    def delete_many(self, where: Any = None) -> SimpleNamespace:
        self.delete_calls.append({"where": where})
        return SimpleNamespace(successful=3, matches=3)


class FakeWeaviateQuery:
    def __init__(self, data: "FakeWeaviateData") -> None:
        self._data = data

    def fetch_objects(self, limit: int = 500, after: Any = None, return_properties: Any = None) -> SimpleNamespace:
        from dataclasses import dataclass as _dc

        @_dc
        class _Obj:
            properties: Any

        return SimpleNamespace(objects=[
            _Obj(properties={"document_id": d}) for d in sorted(self._data.doc_ids)
        ])


class FakeWeaviateBackend(WeaviateBackend):
    """WeaviateBackend without __init__ (no client); _collection returns fakes."""

    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        self.class_name = "AiPortfolioChunk"
        self._embeddings_fn = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]  # noqa: E731
        self.data = FakeWeaviateData()

    def _collection(self) -> Any:  # noqa: D102
        return SimpleNamespace(
            data=self.data,
            query=FakeWeaviateQuery(self.data),
        )


class FakeChromaRag:
    """Mimics the RAGService surface used by ChromaIndexStore."""

    def __init__(self) -> None:
        self.embedded: list[list[str]] = []
        self.added: dict[str, Any] = {}
        self.cleared_by_source: list[str] = []
        self.collection_cleared = False
        self._collection = SimpleNamespace(
            get=lambda **kw: {"ids": ["c1", "c2"]},
            delete=lambda ids: None,
            add=lambda **kw: self.added.update(kw),
        )

    def _create_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.embedded.append(texts)
        return [[0.5] * 3 for _ in texts]

    def clear_by_source_type(self, source_type: str) -> int:
        self.cleared_by_source.append(source_type)
        return 7

    def clear_collection(self) -> None:
        self.collection_cleared = True


class FakeStore:
    backend_name = "fake"
    calls: list[str] = []
    added: dict[str, Any] = {}

    def embed(self, texts: list[str]) -> list[list[float]]:  # noqa: D102
        self.calls.append("embed")
        return [[0.0] * 2 for _ in texts]

    def delete_document_chunks(self, document_id: str) -> int:  # noqa: D102
        self.calls.append(f"delete:{document_id}")
        return 3

    def add_chunks(self, ids, documents, embeddings, metadatas) -> None:  # noqa: ANN001, D102
        self.calls.append("add")
        self.added = {
            "ids": ids,
            "documents": documents,
            "embeddings": embeddings,
            "metadatas": metadatas,
        }

    def clear_by_source_type(self, source_type: str) -> int:  # noqa: D102
        self.calls.append(f"clear:{source_type}")
        return 1

    def clear_collection(self) -> None:  # noqa: D102
        self.calls.append("clear_collection")


def test_weaviate_insert_errors_not_swallowed() -> None:
    print("[weaviate insert partial-failure raises]")
    backend = FakeWeaviateBackend()
    backend.data.insert_errors = {1: SimpleNamespace(message="invalid object")}
    store = WeaviateIndexStore(backend)
    try:
        store.add_chunks(["i1"], ["text"], [[0.1]], [{"document_id": "i1"}])
        check("partial insert failure raises", False, "no RuntimeError")
    except RuntimeError as exc:
        check("partial insert failure raises", "1/1 objects failed" in str(exc), str(exc))
    # store visible doc ids
    backend2 = FakeWeaviateBackend()
    backend2.data.doc_ids = {"a", "b", "c"}
    ids = WeaviateIndexStore(backend2).all_document_ids()
    check("all_document_ids", ids == {"a", "b", "c"}, str(ids))


def test_resolution() -> None:
    print("[resolution]")
    chroma_like = SimpleNamespace(backend_name="chroma", add_chunks=lambda *a, **k: None)
    weav_like = FakeWeaviateBackend()
    store_c = index_store_for(chroma_like)
    store_w = index_store_for(weav_like)
    check("chroma -> ChromaIndexStore", isinstance(store_c, ChromaIndexStore))
    check("weaviate -> WeaviateIndexStore", isinstance(store_w, WeaviateIndexStore))
    try:
        index_store_for(SimpleNamespace(backend_name="magic"))
        check("non-writable backend rejected", False, "no ValueError")
    except ValueError as exc:
        check("non-writable backend rejected", "no index_store" in str(exc), str(exc))


def test_weaviate_add_chunks() -> None:
    print("[weaviate add_chunks]")
    backend = FakeWeaviateBackend()
    store = WeaviateIndexStore(backend)
    store.add_chunks(
        ids=["doc1_chunk_0", "doc1_chunk_1"],
        documents=["hello world", "second chunk"],
        embeddings=[[0.1] * 4, [0.2] * 4],
        metadatas=[
            {
                "source": "README.md",
                "document_id": "doc1",
                "source_type": "github_repo",
                "repo": "owner/repo",
                "chunk_index": 0,
                "total_chunks": 2,
                "chunk_length": 11,
                "visibility": "public",
            },
            {"source": "README.md", "document_id": "doc1", "chunk_index": "1",
             "total_chunks": "2", "chunk_length": "12"},
        ],
    )
    inserted = [obj.properties for obj in backend.data.inserted]
    uu = [obj.uuid for obj in backend.data.inserted]
    vv = [obj.vector for obj in backend.data.inserted]
    check("inserted two objects", len(inserted) == 2, str(len(inserted)))
    first = inserted[0]
    check("text property", first["text"] == "hello world", str(first.get("text")))
    check("repo property", first["repo"] == "owner/repo", str(first.get("repo")))
    check("int cast chunk_index", first["chunk_index"] == 0, repr(first.get("chunk_index")))
    check("int cast total_chunks", first["total_chunks"] == 2, repr(first.get("total_chunks")))
    second = inserted[1]
    check("string numerics cast", second["chunk_index"] == 1, repr(second.get("chunk_index")))
    check("empty visibility skipped", "visibility" not in second, str(second.keys()))
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "ai-portfolio:doc1_chunk_0"))
    check("deterministic uuid", str(uu[0]) == expected, str(uu))
    check("uuid2 valid", str(uu[1]).count("-") == 4, str(uu[1]))
    check("vector aligned", list(vv[0]) == [0.1] * 4, str(vv[0]))
    again = WeaviateBackend._chunk_uuid("doc1_chunk_0")
    check("uuid stable across calls", again == expected, again)


def test_weaviate_deletes() -> None:
    print("[weaviate delete methods]")
    backend = FakeWeaviateBackend()
    store = WeaviateIndexStore(backend)
    n = store.delete_document_chunks("doc1")
    check("delete_document_chunks count", n == 3, str(n))
    n2 = store.clear_by_source_type("knowledge_json")
    check("clear_by_source_type count", n2 == 3, str(n2))
    check("two delete_many calls", len(backend.data.delete_calls) == 2)
    backend2 = FakeWeaviateBackend()
    n3 = WeaviateIndexStore(backend2).delete_document_chunks("")
    check("empty document_id -> 0", n3 == 0, str(n3))
    check("no delete call for empty id", len(backend2.data.delete_calls) == 0)


def test_chroma_store_delegation() -> None:
    print("[chroma store]")
    rag = FakeChromaRag()
    store = ChromaIndexStore(rag)  # type: ignore[arg-type]
    check("backend_name chroma", store.backend_name == "chroma")
    vecs = store.embed(["a", "b"])
    check("embed delegates", vecs == [[0.5] * 3, [0.5] * 3], str(vecs))
    store.add_chunks(["i1"], ["text"], [[0.1]], [{"document_id": "i1"}])
    check("add delegation", rag.added.get("documents") == ["text"], str(rag.added))
    check("clear_by_source_type delegation",
          store.clear_by_source_type("github_x") == 7 and rag.cleared_by_source == ["github_x"])
    store.clear_collection()
    check("clear_collection delegation", rag.collection_cleared is True)
    check("delete_document_chunks counts",
          store.delete_document_chunks("d") == 2, "expected 2 ids from fake get")


def test_indexer_uses_store() -> None:
    print("[indexer -> store]")
    store = FakeStore()
    store.calls = []
    indexer = KnowledgeBaseIndexer(store=store)  # type: ignore[arg-type]
    doc = KnowledgeDocument(id="docX", title="Doc X", content="A" * 120,
                            category="github_repo", url="https://example.com/x")
    created = indexer.index_document(doc, chunk_size=50, chunk_overlap=10)
    check("chunk count", created == 3, str(created))  # ceil over 120 with overlap 10
    check("delete before add", store.calls[0] == "delete:docX", str(store.calls))
    check("embed called", store.calls[1] == "embed", str(store.calls))
    added = store.added
    check("ids shape", added["ids"] == ["docX_chunk_0", "docX_chunk_1", "docX_chunk_2"],
          str(added["ids"]))
    meta = added["metadatas"][0]
    check("metadata document_id", meta["document_id"] == "docX", str(meta))
    check("total_chunks metadata", meta["total_chunks"] == 3, str(meta.get("total_chunks")))
    check("url metadata", meta["url"] == "https://example.com/x", str(meta.get("url")))
    check("chunk_length matches", meta["chunk_length"] == len(added["documents"][0]))


def test_index_store_contract() -> None:
    print("[IndexStore protocol]")
    for cls in (ChromaIndexStore, WeaviateIndexStore):
        for method in ("embed", "delete_document_chunks", "add_chunks",
                       "clear_by_source_type", "clear_collection"):
            check(f"{cls.__name__}.{method}", hasattr(cls, method) or method == "embed"
                  or method == "delete_document_chunks" or method == "add_chunks"
                  or method == "clear_by_source_type" or method == "clear_collection")
    check("IndexStore importable", IndexStore is not None)


if __name__ == "__main__":
    test_weaviate_insert_errors_not_swallowed()
    test_resolution()
    test_weaviate_add_chunks()
    test_weaviate_deletes()
    test_chroma_store_delegation()
    test_indexer_uses_store()
    test_index_store_contract()
    print(f"\nPASSED {len(PASS)} / FAILED {len(FAIL)}")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        sys.exit(1)