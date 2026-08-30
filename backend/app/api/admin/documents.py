"""
Documents console API (§4.5б, поз. 3).

Read-only documents view: list, card (passport/operation/preview),
full text, chunks of the active vector backend.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.documents_console_service import DocumentsConsoleService

router = APIRouter()


@router.get("/knowledge-base/documents")
async def list_documents(
    source_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=500, ge=1, le=1000),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Documents (PG) with per-document chunk counts of the active backend."""
    return DocumentsConsoleService(db).list_documents(
        source_id=source_id, search=search, limit=limit
    )


@router.get("/knowledge-base/documents/{doc_id}")
async def get_document(
    doc_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Document card: passport + operation + text preview."""
    return DocumentsConsoleService(db).get_document(doc_id)


@router.get("/knowledge-base/documents/{doc_id}/text")
async def get_document_text(
    doc_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Full document text (preview panel «Открыть»)."""
    return DocumentsConsoleService(db).get_document_text(doc_id)


@router.get("/knowledge-base/documents/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Chunks of the document in the active backend, ordered by chunk_index."""
    return DocumentsConsoleService(db).get_document_chunks(doc_id, limit=limit)