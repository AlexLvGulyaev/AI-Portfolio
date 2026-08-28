"""
Content / Knowledge Base workspace for admin console.

Provides CRUD for ProjectCards and KnowledgeSources, ChromaDB status,
and manual synchronization into ChromaDB.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import SessionLocal, get_db
from app.services.admin.kb_admission_console_service import AdmissionConsoleService
from app.services.admin.knowledge_base_service import KnowledgeBaseService

router = APIRouter()


class KnowledgeSourceCreate(BaseModel):
    source_type: str = Field(..., pattern=r"^(github_repo|local_directory|local_file)$")
    identifier: str = Field(..., min_length=1, max_length=500)
    display_name: str | None = Field(None, max_length=200)
    branch: str | None = Field(default="main")
    base_path: str | None = None
    is_enabled: bool = True
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    # Note: admission_status is not client-settable on create; every new
    # source starts as "pending" (fail-closed) and must be approved through
    # the Admission Console approval workflow (§4.5а).


class KnowledgeSourceUpdate(BaseModel):
    source_type: str | None = Field(None, pattern=r"^(github_repo|local_directory|local_file)$")
    identifier: str | None = Field(None, min_length=1, max_length=500)
    display_name: str | None = Field(None, max_length=200)
    branch: str | None = None
    base_path: str | None = None
    is_enabled: bool | None = None
    # These fields are accepted by the schema ONLY to be rejected by the
    # endpoint with 409 + machine-readable reason (§4.5а double protection):
    # admission state changes go through dedicated Admission Console
    # endpoints, never through a generic PATCH. They are never applied.
    admission_status: str | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None


class DraftPatternsUpdate(BaseModel):
    """Draft selection rules (working copy; effective on approval only)."""

    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None


class ProjectCardCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    short_description: str = Field(..., min_length=1)
    category: str = "cases"
    tags: list[str] = Field(default_factory=list)
    display_order: int = 0
    show_on_homepage: int = Field(default=0, ge=0, le=4)
    is_visible: bool = True
    knowledge_content: str | None = None
    external_url: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def ensure_tags_list(cls, value):
        if value is None:
            return []
        return value


class ProjectCardUpdate(BaseModel):
    slug: str | None = Field(None, min_length=1, max_length=100)
    title: str | None = Field(None, min_length=1, max_length=200)
    short_description: str | None = Field(None, min_length=1)
    category: str | None = None
    tags: list[str] | None = None
    display_order: int | None = None
    show_on_homepage: int | None = Field(None, ge=0, le=4)
    is_visible: bool | None = None
    knowledge_content: str | None = None
    external_url: str | None = None


@router.get("/knowledge-base/status")
async def get_kb_status(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return ChromaDB status."""
    service = KnowledgeBaseService(db)
    return service.get_chromadb_status()


@router.get("/knowledge-base/sources")
async def list_sources(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all knowledge sources with admission-console metadata."""
    service = AdmissionConsoleService(db)
    return {"items": service.list_sources_console()}


@router.post("/knowledge-base/sources")
async def create_source(
    data: KnowledgeSourceCreate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new knowledge source."""
    service = KnowledgeBaseService(db)
    created = service.create_source(data.model_dump(exclude_unset=True))
    console = AdmissionConsoleService(db)
    console._log_event(UUID(created["id"]), "created", f"Источник добавлен: {created['identifier']}", None)
    db.commit()
    return created


@router.get("/knowledge-base/sources/{source_id}")
async def get_source(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get a single knowledge source."""
    service = KnowledgeBaseService(db)
    return service.get_source(source_id)


@router.patch("/knowledge-base/sources/{source_id}")
async def update_source(
    source_id: UUID,
    data: KnowledgeSourceUpdate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a knowledge source.

    Double protection (§4.5а): even if a client bypasses the console UI,
    admission state cannot be changed through this endpoint — it is
    rejected with 409 and a machine-readable reason.
    """
    payload = data.model_dump(exclude_unset=True)
    for guarded in ("admission_status", "include_patterns", "exclude_patterns"):
        if guarded in payload:
            raise HTTPException(
                409,
                {
                    "reason_code": "use_admission_actions",
                    "message": "Изменение правил и статуса допуска — только через Admission Console",
                },
            )
    service = KnowledgeBaseService(db)
    return service.update_source(source_id, payload)


@router.delete("/knowledge-base/sources/{source_id}")
async def delete_source(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a knowledge source."""
    service = KnowledgeBaseService(db)
    service.delete_source(source_id)
    return {"ok": True}


@router.get("/knowledge-base/sources/{source_id}/admission-preview")
async def preview_source_admission(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Preview admission-gate file selection for a GitHub source.

    Read-only: applies the same selection as the real sync and returns
    per-file decisions. No chunking, embeddings, ChromaDB writes, reindex,
    or admission status changes.
    """
    service = KnowledgeBaseService(db)
    return service.preview_source_admission(source_id)


@router.post("/knowledge-base/sources/{source_id}/admission-previews")
async def build_admission_preview(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Build and persist an immutable admission preview from the draft rules.

    Networked read of GitHub (discovery + head commit): no sync, no
    ChromaDB writes, no admission status changes.
    """
    service = AdmissionConsoleService(db)
    return service.create_preview(source_id)


@router.get("/knowledge-base/sources/{source_id}/admission-previews/latest")
async def get_latest_admission_preview(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return the most recent admission preview (ready or error)."""
    service = AdmissionConsoleService(db)
    return service.get_latest_preview(source_id)


@router.patch("/knowledge-base/sources/{source_id}/draft-patterns")
async def update_draft_patterns(
    source_id: UUID,
    data: DraftPatternsUpdate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Persist the draft selection rules (working copy, not effective)."""
    service = AdmissionConsoleService(db)
    return service.update_draft_patterns(
        source_id, data.include_patterns, data.exclude_patterns
    )


@router.post("/knowledge-base/sources/{source_id}/draft-patterns/reset")
async def reset_draft_patterns(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Discard the draft and revert to the effective (approved) rules."""
    service = AdmissionConsoleService(db)
    return service.reset_draft_patterns(source_id)


@router.post("/knowledge-base/sources/{source_id}/approve")
async def approve_source(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve the latest ready preview as the effective composition.

    Returns 409 + machine-readable reason when the preview is missing,
    not ready, stale (patterns or commit changed), or already approved.
    Does NOT trigger sync/reindex.
    """
    service = AdmissionConsoleService(db)
    return service.approve_source(source_id)


@router.post("/knowledge-base/sources/{source_id}/block")
async def block_source(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Block a source: it stops being indexed on future syncs."""
    service = AdmissionConsoleService(db)
    return service.block_source(source_id)


@router.post("/knowledge-base/sources/{source_id}/unblock")
async def unblock_source(
    source_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unblock a source: restores the previous approved composition if any."""
    service = AdmissionConsoleService(db)
    return service.unblock_source(source_id)


@router.get("/knowledge-base/sources/{source_id}/admission-events")
async def list_admission_events(
    source_id: UUID,
    limit: int = 50,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return the admission decision history for a source."""
    service = AdmissionConsoleService(db)
    return {"items": service.list_events(source_id, limit)}


@router.post("/knowledge-base/sync")
async def sync_knowledge_base(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger a background knowledge base synchronization."""
    service = KnowledgeBaseService(db)
    job = service.start_sync_job()
    job_id = UUID(job["job_id"])

    def _run_sync(job_id: UUID) -> None:
        sync_db = SessionLocal()
        try:
            sync_service = KnowledgeBaseService(sync_db)
            sync_service.sync_knowledge_base(job_id)
        finally:
            sync_db.close()

    asyncio.create_task(asyncio.to_thread(_run_sync, job_id))
    return job


@router.get("/knowledge-base/sync/{job_id}")
async def get_sync_job(
    job_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return status of a background sync job."""
    service = KnowledgeBaseService(db)
    return service.get_sync_job(job_id)


@router.get("/knowledge-base/project-cards")
async def list_project_cards(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all project cards."""
    service = KnowledgeBaseService(db)
    return {"items": service.list_project_cards()}


@router.post("/knowledge-base/project-cards")
async def create_project_card(
    data: ProjectCardCreate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new project card."""
    service = KnowledgeBaseService(db)
    return service.create_project_card(data.model_dump(exclude_unset=True))


@router.get("/knowledge-base/project-cards/{card_id}")
async def get_project_card(
    card_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get a single project card."""
    service = KnowledgeBaseService(db)
    return service.get_project_card(card_id)


@router.patch("/knowledge-base/project-cards/{card_id}")
async def update_project_card(
    card_id: UUID,
    data: ProjectCardUpdate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a project card."""
    service = KnowledgeBaseService(db)
    return service.update_project_card(card_id, data.model_dump(exclude_unset=True))


@router.delete("/knowledge-base/project-cards/{card_id}")
async def delete_project_card(
    card_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a project card."""
    service = KnowledgeBaseService(db)
    service.delete_project_card(card_id)
    return {"ok": True}


@router.get("/knowledge-base/project-cards/{card_id}/chunks")
async def get_project_card_chunks(
    card_id: UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return ChromaDB chunks associated with a project card."""
    service = KnowledgeBaseService(db)
    return {"items": service.get_project_card_chunks(card_id)}
