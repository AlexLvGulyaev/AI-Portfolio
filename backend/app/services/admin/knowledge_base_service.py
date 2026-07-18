"""
Knowledge Base service for admin console.

Manages ProjectCards, KnowledgeSources, ChromaDB status, and manual sync.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeSource, KnowledgeSyncJob, ProjectCard
from app.services.rag.knowledge_base_indexer import KnowledgeBaseIndexer, KnowledgeDocument
from app.services.rag.rag_service import RAGService


class KnowledgeBaseService:
    """Admin Knowledge Base service."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # ChromaDB status
    # ------------------------------------------------------------------

    def get_chromadb_status(self) -> dict[str, Any]:
        """Return current ChromaDB collection status."""
        try:
            rag = RAGService()
            return {
                "status": "ok",
                "collection_name": rag.config.collection_name,
                "embedding_model": rag.config.embedding_model,
                "chunks": rag.count_documents(),
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

    # ------------------------------------------------------------------
    # KnowledgeSource CRUD
    # ------------------------------------------------------------------

    def list_sources(self) -> list[dict[str, Any]]:
        """Return all configured knowledge sources."""
        rows = self._db.scalars(select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc())).all()
        return [self._source_to_dict(row) for row in rows]

    def get_source(self, source_id: UUID) -> dict[str, Any]:
        """Return a single knowledge source by ID."""
        row = self._db.get(KnowledgeSource, source_id)
        if not row:
            raise HTTPException(404, "Knowledge source not found")
        return self._source_to_dict(row)

    def create_source(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new knowledge source."""
        row = KnowledgeSource(
            id=uuid4(),
            source_type=data.get("source_type", "local_file"),
            identifier=data["identifier"],
            branch=data.get("branch"),
            base_path=data.get("base_path"),
            is_enabled=data.get("is_enabled", True),
            last_sync_status="pending",
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    def update_source(self, source_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing knowledge source."""
        row = self._db.get(KnowledgeSource, source_id)
        if not row:
            raise HTTPException(404, "Knowledge source not found")

        for key in ("source_type", "identifier", "branch", "base_path", "is_enabled"):
            if key in data:
                setattr(row, key, data[key])
        row.updated_at = datetime.now(timezone.utc)

        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    def delete_source(self, source_id: UUID) -> None:
        """Delete a knowledge source."""
        row = self._db.get(KnowledgeSource, source_id)
        if not row:
            raise HTTPException(404, "Knowledge source not found")
        self._db.delete(row)
        self._db.commit()

    # ------------------------------------------------------------------
    # ProjectCard CRUD
    # ------------------------------------------------------------------

    def list_project_cards(self) -> list[dict[str, Any]]:
        """Return all project cards ordered by display_order."""
        rows = self._db.scalars(
            select(ProjectCard).order_by(ProjectCard.display_order.asc(), ProjectCard.title.asc())
        ).all()
        return [self._card_to_dict(row) for row in rows]

    def get_project_card(self, card_id: UUID) -> dict[str, Any]:
        """Return a single project card by ID."""
        row = self._db.get(ProjectCard, card_id)
        if not row:
            raise HTTPException(404, "Project card not found")
        return self._card_to_dict(row)

    def get_project_card_chunks(self, card_id: UUID) -> list[dict[str, Any]]:
        """Return ChromaDB chunks associated with a project card."""
        row = self._db.get(ProjectCard, card_id)
        if not row:
            raise HTTPException(404, "Project card not found")

        try:
            rag = RAGService()
            return rag.get_chunks_by_metadata(
                where={
                    "$and": [
                        {"source_type": {"$eq": "project_card"}},
                        {"slug": {"$eq": row.slug}},
                    ]
                },
                limit=100,
            )
        except Exception as exc:
            raise HTTPException(500, f"Failed to load ChromaDB chunks: {exc}")

    def create_project_card(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new project card."""
        slug = data.get("slug", "")
        existing = self._db.scalars(select(ProjectCard).where(ProjectCard.slug == slug).limit(1)).first()
        if existing:
            raise HTTPException(409, f"Project card with slug '{slug}' already exists")

        row = ProjectCard(
            id=uuid4(),
            slug=slug,
            title=data["title"],
            short_description=data["short_description"],
            category=data.get("category", "cases"),
            tags=data.get("tags", []),
            display_order=data.get("display_order", 0),
            show_on_homepage=data.get("show_on_homepage", 0),
            is_visible=data.get("is_visible", True),
            knowledge_content=data.get("knowledge_content"),
            external_url=data.get("external_url"),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._card_to_dict(row)

    def update_project_card(self, card_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing project card."""
        row = self._db.get(ProjectCard, card_id)
        if not row:
            raise HTTPException(404, "Project card not found")

        for key in (
            "slug",
            "title",
            "short_description",
            "category",
            "tags",
            "display_order",
            "show_on_homepage",
            "is_visible",
            "knowledge_content",
            "external_url",
        ):
            if key in data:
                setattr(row, key, data[key])
        row.updated_at = datetime.now(timezone.utc)

        self._db.commit()
        self._db.refresh(row)
        return self._card_to_dict(row)

    def delete_project_card(self, card_id: UUID) -> None:
        """Delete a project card."""
        row = self._db.get(ProjectCard, card_id)
        if not row:
            raise HTTPException(404, "Project card not found")
        self._db.delete(row)
        self._db.commit()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync_knowledge_base(self) -> dict[str, Any]:
        """Run a manual knowledge base synchronization into ChromaDB."""
        job = KnowledgeSyncJob(
            id=uuid4(),
            triggered_by="manual",
            status="running",
            started_at=datetime.now(timezone.utc),
            stats={"documents_processed": 0, "chunks_created": 0, "errors": []},
        )
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)

        overall_stats = {"documents_processed": 0, "chunks_created": 0, "errors": []}

        try:
            rag = RAGService()
            indexer = KnowledgeBaseIndexer(rag_service=rag)

            # Clear existing index
            rag.clear_collection()

            # 1. Index the canonical knowledge.json file if it exists
            knowledge_json = Path("knowledge_base/knowledge.json")
            if knowledge_json.exists():
                file_stats = indexer.index_json_file(knowledge_json, clear_existing=False)
                overall_stats["documents_processed"] += file_stats.documents_processed
                overall_stats["chunks_created"] += file_stats.chunks_created
                overall_stats["errors"].extend(file_stats.errors)

            # 2. Index enabled project cards
            cards = self._db.scalars(
                select(ProjectCard).where(
                    ProjectCard.is_visible.is_(True),
                    ProjectCard.knowledge_content.isnot(None),
                )
            ).all()

            for card in cards:
                content = card.knowledge_content or ""
                if not content.strip():
                    continue
                doc = KnowledgeDocument(
                    id=f"project_card_{card.slug}",
                    title=card.title,
                    content=content,
                    category=card.category,
                    url=card.external_url,
                    metadata={
                        "source_type": "project_card",
                        "slug": card.slug,
                        "tags": card.tags or [],
                    },
                )
                try:
                    chunks = indexer.index_document(doc)
                    overall_stats["documents_processed"] += 1
                    overall_stats["chunks_created"] += chunks
                except Exception as exc:
                    error_msg = f"project_card_{card.slug}: {str(exc)}"
                    overall_stats["errors"].append(error_msg)

            # 3. Update source sync status for enabled sources
            self._db.query(KnowledgeSource).filter(KnowledgeSource.is_enabled.is_(True)).update(
                {
                    "last_sync_at": datetime.now(timezone.utc),
                    "last_sync_status": "success" if not overall_stats["errors"] else "error",
                    "last_sync_error": "\n".join(overall_stats["errors"]) if overall_stats["errors"] else None,
                    "updated_at": datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )

            job.status = "success" if not overall_stats["errors"] else "error"
            job.stats = overall_stats
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = "\n".join(overall_stats["errors"]) if overall_stats["errors"] else None

        except Exception as exc:
            job.status = "error"
            job.error_message = f"{type(exc).__name__}: {exc}"
            job.stats = overall_stats
            job.finished_at = datetime.now(timezone.utc)

        self._db.commit()
        self._db.refresh(job)

        return {
            "job_id": str(job.id),
            "status": job.status,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "stats": job.stats,
            "error_message": job.error_message,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _source_to_dict(self, row: KnowledgeSource) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "source_type": row.source_type,
            "identifier": row.identifier,
            "branch": row.branch,
            "base_path": row.base_path,
            "is_enabled": row.is_enabled,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "last_sync_status": row.last_sync_status,
            "last_sync_error": row.last_sync_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _card_to_dict(self, row: ProjectCard) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "slug": row.slug,
            "title": row.title,
            "short_description": row.short_description,
            "category": row.category,
            "tags": row.tags or [],
            "display_order": row.display_order,
            "show_on_homepage": row.show_on_homepage,
            "is_visible": row.is_visible,
            "knowledge_content": row.knowledge_content,
            "external_url": row.external_url,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
