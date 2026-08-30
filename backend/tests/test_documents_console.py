"""
Unit-тесты консоли «Документы» (task 2026-08-30, §4.5б поз. 3):

- DocumentsConsoleService: список (счётчики чанков активного бэкенда, degraded
  при недоступности), карточка (ПАСПОРТ/ЭКСПЛУАТАЦИЯ/превью), полный текст,
  чанки из активного бэкенда, 404;
- WeaviateBackend.count_document_chunks / chunk_counts_by_document /
  list_document_chunks: разбор формы ответа aggregate/fetch_objects (моки).

Сессия БД и weaviate-клиент мокаются (конвенция suite — без живой БД/TestClient).
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from app.services.admin.documents_console_service import (
    CHUNK_PREVIEW_CHARS,
    DocumentsConsoleService,
)


def _doc_row(doc_id, source_id, **kw):
    content = kw.pop("content", "строка 1\nстрока 2\n" * 40)
    return SimpleNamespace(
        id=doc_id,
        source_id=source_id,
        path=kw.pop("path", "docs/readme.md"),
        title=kw.pop("title", "README"),
        content=content,
        raw_url=kw.pop("raw_url", "https://raw.example/x"),
        commit_sha=kw.pop("commit_sha", "abc1234"),
        fetched_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )


def _service_with_db(doc=None, source=None, rows=None):
    db = MagicMock()
    svc = DocumentsConsoleService(db)
    svc._db_get = {}
    if doc is not None:
        svc._db_get[doc.id] = doc
    if source is not None:
        svc._db_get[source.id] = source
    db.get.side_effect = lambda model, pk: svc._db_get.get(pk)
    if rows is not None:
        db.execute.return_value.all.return_value = rows
    return svc


def _backend(counts=None, chunks=None, fail=False):
    backend = MagicMock()
    if fail:
        backend.chunk_counts_by_document.side_effect = RuntimeError("down")
        backend.list_document_chunks.side_effect = RuntimeError("down")
    else:
        backend.chunk_counts_by_document.return_value = counts or {}
        backend.list_document_chunks.return_value = chunks or []
    backend.count_document_chunks.return_value = 7
    return backend


def _patch_backend(svc, backend):
    return patch.object(DocumentsConsoleService, "_active_backend", return_value=backend)


# ---------- list_documents ----------

def test_list_documents_merges_chunk_counts():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    doc = _doc_row(doc_id, source_id, content="x" * 50)
    svc = _service_with_db(rows=[(doc, "owner/repo", "github_repo")])
    svc._db.scalar.return_value = 225  # корпусный счётчик (все документы, без фильтров)
    store_key = svc._store_document_key("owner/repo", "github_repo", doc.path)
    assert store_key == "github_owner/repo_docs/readme.md"
    with _patch_backend(svc, _backend(counts={store_key: 12})):
        data = svc.list_documents()
    item = data["items"][0]
    assert item["id"] == str(doc_id)
    assert item["source_identifier"] == "owner/repo"
    assert item["chunk_count"] == 12
    assert item["content_length"] == 50
    assert data["total_documents"] == 225
    assert data["backend"]["backend"] in ("chroma", "weaviate")
    print("PASS: list merges per-document chunk counts from active backend (store key)")


def test_list_documents_survives_backend_outage():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id)
    svc = _service_with_db(rows=[(doc, "owner/repo", "github_repo")])
    with _patch_backend(svc, _backend(fail=True)):
        data = svc.list_documents()
    assert data["items"][0]["chunk_count"] is None
    print("PASS: backend outage degrades to chunk_count=None, list stays usable")


def test_list_documents_search_filters_path():
    svc = _service_with_db(rows=[])
    with _patch_backend(svc, _backend()):
        svc.list_documents(search="readme")
    stmt = svc._db.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "%readme%" in compiled
    print("PASS: search filter reaches the query")


# ---------- get_document ----------

def test_get_document_card_shape():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id, content="a" * 5000)
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    svc = _service_with_db(doc=doc, source=source)
    with _patch_backend(svc, _backend()):
        card = svc.get_document(doc_id)
    assert card["passport"]["title"] == "README"
    assert card["passport"]["source_identifier"] == "owner/repo"
    assert card["operation"]["backend_chunks"] == 7
    assert card["operation"]["in_active_index"] is True
    assert card["text_truncated"] is True
    assert len(card["text_preview"]) <= 1600
    print("PASS: document card returns passport/operation/preview")


def test_get_document_not_in_index():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id)
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    svc = _service_with_db(doc=doc, source=source)
    with patch.object(DocumentsConsoleService, "_safe_chunk_count", return_value=0):
        card = svc.get_document(doc_id)
    assert card["operation"]["in_active_index"] is False
    print("PASS: document missing from index is reported")


# ---------- text / chunks ----------

def test_get_document_text_full():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id, content="полный текст" * 500)
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    svc = _service_with_db(doc=doc, source=source)
    data = svc.get_document_text(doc_id)
    assert data["text"] == doc.content
    assert data["content_length"] == len(doc.content)
    print("PASS: full text endpoint returns untruncated content")


def test_get_document_chunks_sorted_and_trimmed():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id)
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    svc = _service_with_db(doc=doc, source=source)
    chunks = [
        {"id": "w2", "content": "y" * (CHUNK_PREVIEW_CHARS + 100),
         "metadata": {"chunk_index": 2, "total_chunks": 3, "document_id": str(doc_id)}},
        {"id": "w1", "content": "x" * 10,
         "metadata": {"chunk_index": 1, "total_chunks": 3, "document_id": str(doc_id)}},
    ]
    with _patch_backend(svc, _backend(chunks=chunks)):
        data = svc.get_document_chunks(doc_id)
    assert [c["chunk_index"] for c in data["items"]] == [1, 2]
    assert data["total"] == 2
    assert all("document_id" not in c for c in data["items"])
    assert all(len(c["preview"]) <= CHUNK_PREVIEW_CHARS for c in data["items"])
    print("PASS: chunks sorted by chunk_index, previews trimmed")


def test_get_document_chunks_backend_error_is_500():
    doc_id, source_id = uuid.uuid4(), uuid.uuid4()
    doc = _doc_row(doc_id, source_id)
    source = SimpleNamespace(id=source_id, identifier="owner/repo", display_name="Repo", source_type="github_repo")
    svc = _service_with_db(doc=doc, source=source)
    with _patch_backend(svc, _backend(fail=True)):
        with pytest.raises(HTTPException) as exc_info:
            svc.get_document_chunks(doc_id)
    assert exc_info.value.status_code == 500
    print("PASS: backend failure during chunk listing -> HTTP 500")


# ---------- WeaviateBackend response parsing ----------

def _weaviate_fixture():
    from app.services.rag.weaviate_backend import WeaviateBackend

    backend = WeaviateBackend.__new__(WeaviateBackend)
    backend.class_name = "AiPortfolioChunk"
    coll = MagicMock()
    backend._client = MagicMock()
    backend._client.collections.get.return_value = coll
    return backend, coll


def test_weaviate_count_document_chunks_parses_group():
    backend, coll = _weaviate_fixture()
    coll.aggregate.over_all.return_value = SimpleNamespace(
        groups=[SimpleNamespace(
            grouped_by=SimpleNamespace(value="doc-1"), total_count=5
        )]
    )
    assert backend.count_document_chunks("doc-1") == 5
    print("PASS: count_document_chunks reads aggregate group total_count")


def test_weaviate_chunk_counts_by_document_parses_groups():
    backend, coll = _weaviate_fixture()
    coll.aggregate.over_all.return_value = SimpleNamespace(groups=[
        SimpleNamespace(grouped_by=SimpleNamespace(value="doc-1"), total_count=5),
        SimpleNamespace(grouped_by=SimpleNamespace(value="doc-2"), total_count=0),
    ])
    assert backend.chunk_counts_by_document() == {"doc-1": 5, "doc-2": 0}
    print("PASS: chunk_counts_by_document maps grouped aggregate")


def test_weaviate_list_document_chunks_sorts_and_shapes():
    from weaviate.classes.query import Filter
    import inspect

    backend, coll = _weaviate_fixture()
    coll.query.fetch_objects.return_value = SimpleNamespace(objects=[
        SimpleNamespace(uuid="u2", properties={
            "text": "second", "chunk_id": "c2", "document_id": "doc-1",
            "chunk_index": 1, "total_chunks": 2, "chunk_length": 6,
        }),
        SimpleNamespace(uuid="u1", properties={
            "text": "first", "chunk_id": "c1", "document_id": "doc-1",
            "chunk_index": 0, "total_chunks": 2, "chunk_length": 5,
        }),
    ])
    items = backend.list_document_chunks("doc-1")
    assert [i["id"] for i in items] == ["u1", "u2"], items
    assert items[0]["content"] == "first"
    assert items[0]["metadata"]["chunk_index"] == 0
    print("PASS: list_document_chunks sorts by chunk_index, hides raw text key")

if __name__ == "__main__":
    import inspect as _i
    mod = sys.modules[__name__]
    tests = [v for k, v in vars(mod).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests")