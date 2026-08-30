"""
Documents console service (§4.5б, поз. 3).

Read-only view over knowledge_documents: the document does not live its own
life — it is part of a source (management stays in the Sources console).
Passport / operation / text preview / chunks of the ACTIVE backend.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeDocument, KnowledgeSource

PREVIEW_CHARS = 1600
CHUNK_PREVIEW_CHARS = 480


class DocumentsConsoleService:
    """Read-only documents listing with chunk data from the active backend."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Retrieval backend access
    # ------------------------------------------------------------------

    def _active_backend(self) -> Any:
        """Currently active vector backend via retrieval_manager."""
        from app.services.rag.retrieval_manager import get_retrieval_manager

        return get_retrieval_manager().get_backend()

    def _backend_overview(self) -> dict[str, Any]:
        """Data for the narrow «active backend» panel of the console."""
        from app.services.rag.retrieval_manager import get_retrieval_manager

        rm = get_retrieval_manager()
        name = rm.effective_backend()
        chunks = None
        backend_state = "unknown"
        try:
            probe = rm.probe_backend(name)
            backend_state = "ok" if probe.get("ok") else "error"
            chunks = probe.get("count")
        except Exception:
            backend_state = "error"
        return {
            "backend": name,
            "state": backend_state,
            "chunks": chunks,
        }

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def list_documents(
        self,
        source_id: Optional[UUID] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """List documents (PG) + per-document chunk counts of the active backend."""
        stmt = (
            select(KnowledgeDocument, KnowledgeSource.identifier, KnowledgeSource.source_type)
            .join(KnowledgeSource, KnowledgeDocument.source_id == KnowledgeSource.id)
            .order_by(KnowledgeSource.identifier, KnowledgeDocument.path)
        )
        if source_id is not None:
            stmt = stmt.where(KnowledgeDocument.source_id == source_id)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(KnowledgeDocument.path.ilike(pattern) |
                              KnowledgeDocument.title.ilike(pattern))
        rows = self._db.execute(stmt.limit(int(limit))).all()
        # Корпусный счётчик без фильтров — для тулбар-стрип «N документов»
        # (все документы, не только отчанкованные; решение владельца 30.08.2026).
        total_documents = self._db.scalar(select(func.count(KnowledgeDocument.id)))

        chunk_counts: dict[str, int] = {}
        try:
            chunk_counts = self._active_backend().chunk_counts_by_document()
        except Exception:
            chunk_counts = {}  # list stays usable even if the backend is down

        items = []
        for doc, source_identifier, source_type in rows:
            store_key = self._store_document_key(source_identifier, source_type, doc.path)
            items.append({
                "id": str(doc.id),
                "source_id": str(doc.source_id),
                "source_identifier": source_identifier,
                "path": doc.path,
                "title": doc.title or doc.path.rsplit("/", 1)[-1],
                "commit_sha": doc.commit_sha,
                "fetched_at": doc.fetched_at.isoformat() if doc.fetched_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "content_length": len(doc.content or ""),
                # None = бэкенд недоступен (счетчик не получен); иначе число в активном бэкенде.
                "chunk_count": chunk_counts.get(store_key) if store_key else None,
            })
        return {
            "items": items,
            "total_documents": int(total_documents or 0),
            "backend": self._backend_overview(),
        }

    def get_document(self, doc_id: UUID) -> dict[str, Any]:
        """Document card: passport + operation + short text preview."""
        doc, source = self._load(doc_id)
        store_key = self._store_document_key(
            source.identifier if source else None,
            source.source_type if source else None,
            doc.path,
        )
        chunk_count = self._safe_chunk_count(store_key) if store_key else 0
        return {
            "id": str(doc.id),
            "passport": {
                "title": doc.title or doc.path.rsplit("/", 1)[-1],
                "path": doc.path,
                "source_id": str(doc.source_id),
                "source_identifier": source.identifier if source else None,
                "source_display_name": source.display_name if source else None,
                "raw_url": doc.raw_url,
                "content_length": len(doc.content or ""),
            },
            "operation": {
                "backend_chunks": chunk_count,
                "in_active_index": (chunk_count or 0) > 0,
                "commit_sha": doc.commit_sha,
                "fetched_at": doc.fetched_at.isoformat() if doc.fetched_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            },
            "text_preview": (doc.content or "")[:PREVIEW_CHARS],
            # Длина в код-поинтах считает сервер: JS string.length даёт UTF-16 код-юниты
            "text_preview_length": len((doc.content or "")[:PREVIEW_CHARS]),
            "text_truncated": len(doc.content or "") > PREVIEW_CHARS,
            "backend": self._backend_overview(),
        }

    def get_document_text(self, doc_id: UUID) -> dict[str, Any]:
        """Full document text («Открыть» in the text preview panel)."""
        doc, _ = self._load(doc_id)
        return {
            "id": str(doc.id),
            "title": doc.title or doc.path.rsplit("/", 1)[-1],
            "path": doc.path,
            "raw_url": doc.raw_url,
            "text": doc.content or "",
            "content_length": len(doc.content or ""),
        }

    def get_document_chunks(self, doc_id: UUID, limit: int = 1000) -> dict[str, Any]:
        """Chunks of the document in the ACTIVE backend, ordered by chunk_index."""
        doc, source = self._load(doc_id)
        store_key = self._store_document_key(
            source.identifier if source else None,
            source.source_type if source else None,
            doc.path,
        )
        if store_key is None:
            raise HTTPException(409, "Document has no source; cannot locate its chunks")
        backend = self._active_backend()
        try:
            chunks = backend.list_document_chunks(store_key, limit=limit)
        except Exception as exc:
            raise HTTPException(
                500, f"Failed to load chunks from active backend: {exc}"
            )
        compact = []
        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            content = chunk.get("content") or ""
            meta = {k: v for k, v in meta.items() if k != "document_id"}
            compact.append({
                "id": chunk.get("id"),
                "chunk_index": meta.get("chunk_index"),
                "total_chunks": meta.get("total_chunks"),
                "chunk_length": meta.get("chunk_length") or len(content),
                "preview": content[:CHUNK_PREVIEW_CHARS],
            })
        compact.sort(key=lambda c: (c["chunk_index"] is None, c["chunk_index"] or 0))
        return {
            "items": compact,
            "total": len(compact),
            "backend": self._backend_overview(),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load(
        self, doc_id: UUID
    ) -> tuple[KnowledgeDocument, Optional[KnowledgeSource]]:
        doc = self._db.get(KnowledgeDocument, doc_id)
        if not doc:
            raise HTTPException(404, "Document not found")
        source = self._db.get(KnowledgeSource, doc.source_id)
        return doc, source

    def _store_document_key(self, source_identifier, source_type, path):
        """Composite document id used by the sync pipeline in the vector stores.

        This is IndexerDocument.id (knowledge_base_service: id=f"github_{identifier}_{path}"),
        NOT the PG knowledge_documents UUID — the stores have no knowledge of PG ids.
        """
        if not source_identifier:
            return None
        if source_type == "github_repo":
            return f"github_{source_identifier}_{path}"
        return f"{source_type}_{source_identifier}_{path}"

    def _safe_chunk_count(self, store_key: str) -> Optional[int]:
        try:
            return int(self._active_backend().count_document_chunks(store_key))
        except Exception:
            return None