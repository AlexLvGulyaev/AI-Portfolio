"""
Dashboard service for admin console.

Aggregates system health and content metrics for the admin dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.entities import (
    AIProviderSetting,
    ChatSession,
    KBAdmissionEvent,
    KnowledgeDocument,
    KnowledgeSource,
    KnowledgeSyncJob,
    OperationalLog,
    ProjectCard,
)
from app.services.ai_provider_settings_service import AIProviderSettingsService
from app.services.rag.rag_service import RAGConfig, RAGService


class DashboardService:
    """Collect dashboard metrics for the admin console."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._provider_service = AIProviderSettingsService(db)

    def get_dashboard(self) -> dict[str, Any]:
        """Return aggregated dashboard metrics."""
        pg_status = self._check_postgresql()
        chroma_status = self._check_chromadb()
        weaviate_status = self._check_weaviate()

        return {
            "status": (
                "ok"
                if pg_status == "ok" and chroma_status == "ok" and weaviate_status == "ok"
                else "degraded"
            ),
            "system": {
                "backend": "ok",
                "postgresql": pg_status,
                "chromadb": chroma_status,
                "weaviate": weaviate_status,
            },
            "ai_providers": self._get_ai_provider_metrics(),
            "project_cards": self._get_project_card_metrics(),
            "knowledge_base": self._get_knowledge_base_metrics(),
            "audit": self._get_audit_metrics(),
            "logs": self._get_log_metrics(),
            "conversations": self._get_conversation_metrics(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _check_postgresql(self) -> str:
        """Check PostgreSQL connectivity by running a trivial query."""
        try:
            self._db.execute(select(func.count()).select_from(ProjectCard).limit(1))
            return "ok"
        except SQLAlchemyError as exc:
            return f"error: {type(exc).__name__}"

    def _check_chromadb(self) -> str:
        """Check ChromaDB connectivity by counting documents.

        RAGConfig.from_settings() обязателен: дефолтный RAGConfig указывает на
        старую локальную коллекцию ai_portfolio_knowledge (count=0), а не на
        боевую HTTP-коллекцию из env. Счётчик чанков сохраняется в
        self._chroma_count — панелька «ChromaDB» использует его как примечание.
        """
        self._chroma_count = None
        try:
            rag = RAGService(RAGConfig.from_settings())
            self._chroma_count = int(rag.count_documents())
            return "ok"
        except Exception as exc:
            return f"error: {type(exc).__name__}"

    def _check_weaviate(self) -> str:
        """Check Weaviate backend health via the retrieval manager probe.

        Возвращает статус и (через self._weaviate_probe_count) счётчик чанков
        активной weaviate-коллекции — панелька «Weaviate» использует его как
        примечание.
        """
        self._weaviate_probe_count = None
        try:
            from app.services.rag.retrieval_manager import get_retrieval_manager

            probe = get_retrieval_manager().probe_backend("weaviate")
        except Exception as exc:
            return f"error: {type(exc).__name__}"
        if not probe.get("ok"):
            return "error"
        count = probe.get("count")
        if count is None:
            return "degraded"  # сервер доступен, коллекция не создана
        self._weaviate_probe_count = int(count)
        return "ok"

    def _get_ai_provider_metrics(self) -> dict[str, Any]:
        """Return metrics for configured AI providers."""
        providers = self._provider_service.list_settings()
        active = self._provider_service.get_active()
        fallback = self._provider_service.get_fallback()

        active_provider = None
        if active:
            active_provider = self._provider_service._to_dict(active)

        fallback_provider = None
        if fallback:
            fallback_provider = self._provider_service._to_dict(fallback)

        return {
            "total": len(providers),
            "enabled": sum(1 for p in providers if p.get("is_enabled")),
            "active": active_provider,
            "fallback": fallback_provider,
            "providers": providers,
        }

    def _get_project_card_metrics(self) -> dict[str, Any]:
        """Return project card counts."""
        total = self._db.scalar(select(func.count(ProjectCard.id)))
        visible = self._db.scalar(
            select(func.count(ProjectCard.id)).where(ProjectCard.is_visible.is_(True))
        )
        homepage = self._db.scalar(
            select(func.count(ProjectCard.id)).where(ProjectCard.show_on_homepage > 0)
        )
        return {
            "total": total or 0,
            "visible": visible or 0,
            "homepage": homepage or 0,
        }

    def _get_knowledge_base_metrics(self) -> dict[str, Any]:
        """Return knowledge base source and sync metrics."""
        sources_count = self._db.scalar(select(func.count(KnowledgeSource.id)))
        documents_count = self._db.scalar(select(func.count(KnowledgeDocument.id)))

        last_job = self._db.scalars(
            select(KnowledgeSyncJob)
            .where(KnowledgeSyncJob.finished_at.isnot(None))
            .order_by(KnowledgeSyncJob.finished_at.desc())
            .limit(1)
        ).first()

        return {
            "sources": sources_count or 0,
            "documents": documents_count or 0,
            "chunks": self._weaviate_probe_count,
            "chroma_chunks": self._chroma_count,
            "last_sync_at": last_job.finished_at.isoformat() if last_job and last_job.finished_at else None,
            "last_sync_status": last_job.status if last_job else "pending",
            "last_sync_stats": last_job.stats if last_job else None,
        }

    def _get_audit_metrics(self) -> dict[str, Any]:
        """Return KB admission audit event counts."""
        total = self._db.scalar(select(func.count(KBAdmissionEvent.id)))
        return {"total": total or 0}

    def _get_log_metrics(self) -> dict[str, Any]:
        """Return operational log counts."""
        total = self._db.scalar(select(func.count(OperationalLog.id)))
        return {"total": total or 0}

    def _get_conversation_metrics(self) -> dict[str, Any]:
        """Return chat session counts."""
        total = self._db.scalar(select(func.count(ChatSession.id)))
        active = self._db.scalar(
            select(func.count(ChatSession.id)).where(ChatSession.is_active.is_(True))
        )
        return {
            "total": total or 0,
            "active": active or 0,
        }
