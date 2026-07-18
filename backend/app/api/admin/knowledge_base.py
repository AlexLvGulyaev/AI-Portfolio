"""
Content / Knowledge Base workspace for admin console.

Provides CRUD for ProjectCards and KnowledgeSources, ChromaDB status,
and manual synchronization into ChromaDB.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.knowledge_base_service import KnowledgeBaseService

router = APIRouter()


class KnowledgeSourceCreate(BaseModel):
    source_type: str = Field(..., pattern=r"^(github_repo|local_directory|local_file)$")
    identifier: str = Field(..., min_length=1, max_length=500)
    branch: str | None = None
    base_path: str | None = None
    is_enabled: bool = True


class KnowledgeSourceUpdate(BaseModel):
    source_type: str | None = Field(None, pattern=r"^(github_repo|local_directory|local_file)$")
    identifier: str | None = Field(None, min_length=1, max_length=500)
    branch: str | None = None
    base_path: str | None = None
    is_enabled: bool | None = None


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
    """List all knowledge sources."""
    service = KnowledgeBaseService(db)
    return {"items": service.list_sources()}


@router.post("/knowledge-base/sources")
async def create_source(
    data: KnowledgeSourceCreate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new knowledge source."""
    service = KnowledgeBaseService(db)
    return service.create_source(data.model_dump(exclude_unset=True))


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
    """Update a knowledge source."""
    service = KnowledgeBaseService(db)
    return service.update_source(source_id, data.model_dump(exclude_unset=True))


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


@router.post("/knowledge-base/sync")
async def sync_knowledge_base(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger a manual knowledge base synchronization."""
    service = KnowledgeBaseService(db)
    return service.sync_knowledge_base()


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
