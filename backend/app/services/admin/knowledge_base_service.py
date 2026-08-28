"""
Knowledge Base service for admin console.

Manages ProjectCards, KnowledgeSources, ChromaDB status, and manual sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeSource, KnowledgeSyncJob, ProjectCard
from app.services.admin import kb_admission
from app.services.admin.github_knowledge_source_service import GitHubKnowledgeSourceService
from app.services.rag.knowledge_base_indexer import KnowledgeBaseIndexer, KnowledgeDocument as IndexerDocument
from app.services.rag.rag_service import RAGConfig, RAGService


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
            rag = RAGService(config=RAGConfig.from_settings())
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
        """Create a new knowledge source.

        Admission gate: a new source always starts as "pending" (fail-closed)
        and must be explicitly approved by the owner after review.
        """
        row = KnowledgeSource(
            id=uuid4(),
            source_type=data.get("source_type", "local_file"),
            identifier=data["identifier"],
            branch=data.get("branch") or "main",
            base_path=data.get("base_path"),
            is_enabled=data.get("is_enabled", True),
            admission_status="pending",
            include_patterns=list(data.get("include_patterns") or []),
            exclude_patterns=list(data.get("exclude_patterns") or []),
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

        for key in (
            "source_type",
            "identifier",
            "branch",
            "base_path",
            "is_enabled",
            "admission_status",
            "include_patterns",
            "exclude_patterns",
        ):
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
    # Admission preview (read-only; no KB writes)
    # ------------------------------------------------------------------

    def preview_source_admission(
        self,
        source_id: UUID,
        github_service: Optional[GitHubKnowledgeSourceService] = None,
    ) -> dict[str, Any]:
        """Preview the admission-gate file selection for a GitHub source.

        Read-only operation: lists the actual repository files, applies the
        same selection mechanism used by the real sync, and returns per-file
        decisions. Performs no chunking, no embeddings, no ChromaDB writes,
        no reindex, and no admission status changes.
        """
        row = self._db.get(KnowledgeSource, source_id)
        if not row:
            raise HTTPException(404, "Knowledge source not found")

        owns_service = github_service is None
        service = github_service or GitHubKnowledgeSourceService(self._db)
        try:
            try:
                paths = service.discover_paths(row)
            except Exception as exc:
                raise HTTPException(502, f"Failed to list files from GitHub source: {type(exc).__name__}: {exc}")

            decisions = kb_admission.select_files(
                paths,
                row.admission_status,
                row.include_patterns,
                row.exclude_patterns,
            )
        finally:
            if owns_service:
                service.close()

        included = [d for d in decisions if d.included]
        excluded = [d for d in decisions if not d.included]

        return {
            "source_id": str(row.id),
            "identifier": row.identifier,
            "admission_status": row.admission_status,
            "include_patterns": row.include_patterns or [],
            "exclude_patterns": row.exclude_patterns or [],
            "candidates_total": len(decisions),
            "included_count": len(included),
            "excluded_count": len(excluded),
            "files": [
                {"path": d.path, "decision": "included" if d.included else "excluded", "reason": d.reason}
                for d in decisions
            ],
        }

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def start_sync_job(self) -> dict[str, Any]:
        """Create and persist a new pending sync job."""
        job = KnowledgeSyncJob(
            id=uuid4(),
            triggered_by="manual",
            status="running",
            started_at=datetime.now(timezone.utc),
            stats={
                "documents_processed": 0,
                "chunks_created": 0,
                "sources_processed": 0,
                "sources_skipped": [],
                "skipped_files": [],
                "errors": [],
            },
        )
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return self._job_to_dict(job)

    def get_sync_job(self, job_id: UUID) -> dict[str, Any]:
        """Return a single sync job by ID."""
        row = self._db.get(KnowledgeSyncJob, job_id)
        if not row:
            raise HTTPException(404, "Sync job not found")
        return self._job_to_dict(row)

    def sync_knowledge_base(self, job_id: UUID) -> dict[str, Any]:
        """Run a manual knowledge base synchronization into ChromaDB."""
        job = self._db.get(KnowledgeSyncJob, job_id)
        if not job:
            raise HTTPException(404, "Sync job not found")

        overall_stats = {
            "documents_processed": 0,
            "chunks_created": 0,
            "sources_processed": 0,
            "sources_skipped": [],
            "skipped_files": [],
            "errors": [],
        }

        github_service: Optional[GitHubKnowledgeSourceService] = None

        try:
            rag = RAGService(config=RAGConfig.from_settings())
            indexer = KnowledgeBaseIndexer(rag_service=rag)

            # Clear legacy knowledge_json chunks. GitHub chunks are removed
            # incrementally by index_document via document_id.
            rag.clear_by_source_type("knowledge_json")

            # 1. Index enabled GitHub sources
            github_service = GitHubKnowledgeSourceService(self._db)
            enabled_sources = self._db.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.is_enabled.is_(True),
                    KnowledgeSource.source_type == "github_repo",
                )
            ).all()

            for source in enabled_sources:
                # Admission gate (source level): pending/blocked/unknown sources
                # are not processed at all. A managed skip is not a sync failure.
                admission_ok, admission_reason = kb_admission.source_indexable(source)
                if not admission_ok:
                    overall_stats["sources_skipped"].append({
                        "identifier": source.identifier,
                        "reason": admission_reason,
                    })
                    continue

                overall_stats["sources_processed"] += 1
                try:
                    fetch_result = github_service.fetch_source(source)
                    github_service.save_fetched_files(source.id, fetch_result.files, fetch_result.errors)

                    for skip in fetch_result.skipped:
                        overall_stats["skipped_files"].append(
                            f"github_{source.identifier}_{skip.get('path', '')}: {skip.get('reason')}"
                        )

                    for file in fetch_result.files:
                        doc = IndexerDocument(
                            id=f"github_{source.identifier}_{file.path}",
                            title=file.title or file.path,
                            content=file.content,
                            category="github_repo",
                            url=file.raw_url,
                            metadata={
                                "source_type": "github_repo",
                                "repo": source.identifier,
                                "path": file.path,
                                "commit_sha": file.commit_sha,
                            },
                        )
                        try:
                            chunks = indexer.index_document(doc)
                            overall_stats["documents_processed"] += 1
                            overall_stats["chunks_created"] += chunks
                        except Exception as exc:
                            error_msg = f"github_{source.identifier}_{file.path}: {str(exc)}"
                            overall_stats["errors"].append(error_msg)

                    for error in fetch_result.errors:
                        error_msg = f"github_{source.identifier}_{error.get('path', '')}: {error.get('error_type')} — {error.get('error_message')}"
                        overall_stats["errors"].append(error_msg)

                    self._update_source_sync_status(
                        source.id,
                        "success" if not fetch_result.errors else "error",
                        "\n".join(e.get("error_message", "") for e in fetch_result.errors) if fetch_result.errors else None,
                    )
                except Exception as exc:
                    error_msg = f"source_{source.identifier}: {type(exc).__name__}: {exc}"
                    overall_stats["errors"].append(error_msg)
                    self._update_source_sync_status(source.id, "error", str(exc))

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
                doc = IndexerDocument(
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

            # 3. Mark disabled/idle sources
            self._db.query(KnowledgeSource).filter(
                KnowledgeSource.is_enabled.is_(False)
            ).update(
                {
                    "last_sync_status": "pending",
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

        finally:
            if github_service is not None:
                github_service.close()

        self._db.commit()
        self._db.refresh(job)

        return self._job_to_dict(job)

    def _job_to_dict(self, row: KnowledgeSyncJob) -> dict[str, Any]:
        return {
            "job_id": str(row.id),
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "stats": row.stats,
            "error_message": row.error_message,
        }

    def _update_source_sync_status(
        self,
        source_id: UUID,
        status: str,
        error_message: Optional[str],
    ) -> None:
        """Update sync status for a single knowledge source."""
        from sqlalchemy import update

        self._db.execute(
            update(KnowledgeSource)
            .where(KnowledgeSource.id == source_id)
            .values(
                last_sync_at=datetime.now(timezone.utc),
                last_sync_status=status,
                last_sync_error=error_message,
                updated_at=datetime.now(timezone.utc),
            )
        )
        self._db.commit()

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
            "admission_status": row.admission_status,
            "include_patterns": row.include_patterns or [],
            "exclude_patterns": row.exclude_patterns or [],
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
