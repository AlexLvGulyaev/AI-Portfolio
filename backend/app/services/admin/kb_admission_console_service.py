"""
Admission Console service (§4.5а).

Manages the admission workflow for GitHub knowledge sources:
persistent immutable previews, draft selection rules, approval with
stale-protection (409 + machine-readable reasons), block/unblock, and
decision history events.

Invariants:
- approval is the ONLY operation that changes the effective selection
  patterns (include/exclude on the source row, the ones consumed by sync);
- draft edits and preview builds never touch the effective patterns —
  the previously approved composition stays in force until a new approval;
- approval never triggers sync/reindex and never writes to ChromaDB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    KBAdmissionEvent,
    KBAdmissionPreview,
    KnowledgeSource,
)
from app.services.admin import kb_admission_console as rules
from app.services.admin import kb_admission
from app.services.admin.github_knowledge_source_service import GitHubKnowledgeSourceService


class AdmissionConsoleService:
    """Admission workflow service for the admin console."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Sources list (console-enriched)
    # ------------------------------------------------------------------

    def list_sources_console(self) -> list[dict[str, Any]]:
        """Return all sources with draft/approval metadata and display status."""
        rows = self._db.scalars(
            select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc())
        ).all()
        latest = self._latest_previews()
        items = []
        for row in rows:
            preview = latest.get(row.id)
            items.append({
                **self._source_to_dict(row),
                "display_status": rules.derive_display_status(
                    row.admission_status, preview, row
                ),
                "preview": self._preview_summary(preview),
            })
        return items

    def _preview_summary(self, preview: Optional[KBAdmissionPreview]) -> Optional[dict[str, Any]]:
        if preview is None:
            return None
        return {
            "id": str(preview.id),
            "status": preview.status,
            "commit_sha": preview.commit_sha,
            "candidates_total": preview.candidates_total or 0,
            "included_count": preview.included_count or 0,
            "excluded_count": preview.excluded_count or 0,
            "created_at": preview.created_at.isoformat() if preview.created_at else None,
        }

    def _source_to_dict(self, row: KnowledgeSource) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "source_type": row.source_type,
            "identifier": row.identifier,
            "project_card_id": str(row.project_card_id) if row.project_card_id else None,
            "display_name": row.display_name,
            "branch": row.branch,
            "base_path": row.base_path,
            "is_enabled": row.is_enabled,
            "admission_status": row.admission_status,
            "include_patterns": row.include_patterns or [],
            "exclude_patterns": row.exclude_patterns or [],
            "draft_include_patterns": row.draft_include_patterns,
            "draft_exclude_patterns": row.draft_exclude_patterns,
            "approved_preview_id": str(row.approved_preview_id) if row.approved_preview_id else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "last_sync_status": row.last_sync_status,
            "last_sync_error": row.last_sync_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def _latest_previews(self) -> dict[UUID, KBAdmissionPreview]:
        """Latest preview per source (single query, newest first)."""
        previews = self._db.scalars(
            select(KBAdmissionPreview).order_by(KBAdmissionPreview.created_at.desc())
        ).all()
        latest: dict[UUID, KBAdmissionPreview] = {}
        for preview in previews:
            latest.setdefault(preview.source_id, preview)
        return latest

    # ------------------------------------------------------------------
    # Preview lifecycle
    # ------------------------------------------------------------------

    def create_preview(self, source_id: UUID) -> dict[str, Any]:
        """Build and persist an immutable admission preview from the draft.

        Networked read (GitHub discovery + head commit): performs no sync,
        no ChromaDB writes, no admission status changes.
        """
        row = self._require_source(source_id)
        include_patterns, exclude_patterns = rules.draft_patterns(row)
        effective_patterns = (row.include_patterns or [], row.exclude_patterns or [])

        github = GitHubKnowledgeSourceService(self._db)
        try:
            owner, repo = GitHubKnowledgeSourceService._parse_identifier(row.identifier)
            try:
                commit_sha = github.fetch_head_commit(
                    owner or "", repo or "", row.branch or "main"
                )
            except Exception as exc:
                return self._store_error_preview(
                    row, include_patterns, exclude_patterns,
                    error_code="github_unavailable",
                    error_message=f"Не удалось получить данные GitHub: {type(exc).__name__}: {exc}",
                )
            try:
                paths = github.discover_paths(row)
            except Exception as exc:
                return self._store_error_preview(
                    row, include_patterns, exclude_patterns,
                    error_code="discovery_failed",
                    error_message=f"Не удалось получить список файлов: {type(exc).__name__}: {exc}",
                )
        finally:
            github.close()

        # Preview is ALWAYS computed as if the source may be indexed: the
        # gate is applied with admission="approved" so the owner sees the
        # selection rules at work and not the current approval state.
        decisions = kb_admission.select_files(
            paths,
            kb_admission.ADMISSION_APPROVED,
            include_patterns,
            exclude_patterns,
        )
        included = [d for d in decisions if d.included]
        excluded = [d for d in decisions if not d.included]

        preview = KBAdmissionPreview(
            id=uuid4(),
            source_id=row.id,
            status="ready",
            commit_sha=commit_sha,
            include_patterns=list(include_patterns or []),
            exclude_patterns=list(exclude_patterns or []),
            candidates_total=len(decisions),
            included_count=len(included),
            excluded_count=len(excluded),
            files=[
                {
                    "path": d.path,
                    "decision": "included" if d.included else "excluded",
                    "reason": d.reason,
                    "pattern": self._matched_pattern(d.reason),
                }
                for d in decisions
            ],
        )
        self._db.add(preview)
        self._log_event(
            row.id,
            rules.EVENT_PREVIEW_CREATED,
            f"Preview построен: {len(included)} в KB / {len(excluded)} исключено",
            {"preview_id": str(preview.id), "commit_sha": commit_sha},
        )
        self._db.commit()
        self._db.refresh(preview)
        return self._preview_to_dict(preview)

    @staticmethod
    def _matched_pattern(reason: str) -> Optional[str]:
        """Extract the matched pattern from a decision reason ("included: docs/**")."""
        if ": " in reason:
            return reason.split(": ", 1)[1]
        return None

    def _store_error_preview(
        self,
        row: KnowledgeSource,
        include_patterns: Any,
        exclude_patterns: Any,
        error_code: str,
        error_message: str,
    ) -> dict[str, Any]:
        preview = KBAdmissionPreview(
            id=uuid4(),
            source_id=row.id,
            status="error",
            include_patterns=list(include_patterns or []),
            exclude_patterns=list(exclude_patterns or []),
            error_code=error_code,
            error_message=error_message,
            files=[],
        )
        self._db.add(preview)
        self._log_event(
            row.id,
            rules.EVENT_PREVIEW_FAILED,
            f"Ошибка построения preview: {error_code}",
            {"error_code": error_code, "error_message": error_message},
        )
        self._db.commit()
        self._db.refresh(preview)
        return self._preview_to_dict(preview)

    def get_latest_preview(self, source_id: UUID) -> dict[str, Any]:
        """Return the most recent preview for a source (ready or error)."""
        self._require_source(source_id)
        preview = self._db.scalars(
            select(KBAdmissionPreview)
            .where(KBAdmissionPreview.source_id == source_id)
            .order_by(KBAdmissionPreview.created_at.desc())
            .limit(1)
        ).first()
        if not preview:
            raise HTTPException(404, "Admission preview not found")
        return self._preview_to_dict(preview)

    def _preview_to_dict(self, preview: KBAdmissionPreview) -> dict[str, Any]:
        source = self._db.get(KnowledgeSource, preview.source_id)
        return {
            "id": str(preview.id),
            "source_id": str(preview.source_id),
            "status": preview.status,
            "commit_sha": preview.commit_sha,
            "include_patterns": preview.include_patterns or [],
            "exclude_patterns": preview.exclude_patterns or [],
            "candidates_total": preview.candidates_total or 0,
            "included_count": preview.included_count or 0,
            "excluded_count": preview.excluded_count or 0,
            "files": preview.files or [],
            "error_code": preview.error_code,
            "error_message": preview.error_message,
            "created_at": preview.created_at.isoformat() if preview.created_at else None,
            # Convenience flag: the draft has drifted from this preview's
            # composition (either the draft changed or the preview is older).
            "stale": (source.draft_include_patterns is not None or source.draft_exclude_patterns is not None)
            if source is not None
            else False,
        }

    # ------------------------------------------------------------------
    # Draft rules
    # ------------------------------------------------------------------

    def update_draft_patterns(
        self,
        source_id: UUID,
        include_patterns: Any,
        exclude_patterns: Any,
    ) -> dict[str, Any]:
        """Persist the draft selection rules (fail-closed validation)."""
        row = self._require_source(source_id)

        include = kb_admission.normalize_patterns(include_patterns)
        exclude = kb_admission.normalize_patterns(exclude_patterns)
        if include is None or exclude is None:
            raise HTTPException(
                422,
                {"reason_code": "invalid_patterns", "message": "Паттерны должны быть строками"},
            )

        row.draft_include_patterns = include
        row.draft_exclude_patterns = exclude
        row.updated_at = datetime.now(timezone.utc)
        self._log_event(
            row.id,
            rules.EVENT_DRAFT_UPDATED,
            "Черновик правил изменён",
            {"include_patterns": include, "exclude_patterns": exclude},
        )
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    def reset_draft_patterns(self, source_id: UUID) -> dict[str, Any]:
        """Discard the draft: revert to the effective (approved) rules."""
        row = self._require_source(source_id)
        row.draft_include_patterns = None
        row.draft_exclude_patterns = None
        row.updated_at = datetime.now(timezone.utc)
        self._log_event(row.id, rules.EVENT_DRAFT_RESET, "Черновик правил отменён", None)
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------

    def approve_source(self, source_id: UUID) -> dict[str, Any]:
        """Approve the latest ready preview as the effective composition.

        Triple protection (§4.5а): UI disabled-reasons, this guard (409 +
        machine-readable reason), and the existing admission gate. Approval
        does NOT trigger sync/reindex: the new composition becomes effective
        immediately, ChromaDB content converges on the next explicit sync.
        """
        row = self._require_source(source_id)
        latest = self._db.scalars(
            select(KBAdmissionPreview)
            .where(KBAdmissionPreview.source_id == source_id)
            .order_by(KBAdmissionPreview.created_at.desc())
            .limit(1)
        ).first()

        draft = rules.draft_patterns(row)
        head_sha: Optional[str] = None
        if latest is not None and latest.status == "ready":
            head_sha = self._current_head_sha(row)

        guard = rules.evaluate_approval(
            row.admission_status,
            latest,
            (latest.include_patterns, latest.exclude_patterns) if latest else ([], []),
            draft,
            head_sha,
            row.approved_preview_id,
        )
        if not guard.allowed:
            self._log_event(
                row.id,
                rules.EVENT_APPROVAL_REJECTED,
                f"Одобрение отклонено: {guard.reason_code}",
                {"reason_code": guard.reason_code, "message": guard.message},
            )
            self._db.commit()
            raise HTTPException(
                409,
                {"reason_code": guard.reason_code, "message": guard.message},
            )

        row.admission_status = kb_admission.ADMISSION_APPROVED
        row.include_patterns = list(latest.include_patterns or [])
        row.exclude_patterns = list(latest.exclude_patterns or [])
        row.draft_include_patterns = None
        row.draft_exclude_patterns = None
        row.approved_preview_id = latest.id
        row.approved_at = datetime.now(timezone.utc)
        row.updated_at = row.approved_at

        self._log_event(
            row.id,
            rules.EVENT_APPROVED,
            f"Состав одобрен: {latest.included_count} в KB / {latest.excluded_count} исключено",
            {
                "preview_id": str(latest.id),
                "commit_sha": latest.commit_sha,
                "approved_at": row.approved_at.isoformat(),
            },
        )
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    def _current_head_sha(self, row: KnowledgeSource) -> Optional[str]:
        owner, repo = GitHubKnowledgeSourceService._parse_identifier(row.identifier)
        github = GitHubKnowledgeSourceService(self._db)
        try:
            return github.fetch_head_commit(owner or "", repo or "", row.branch or "main")
        except Exception:
            return None
        finally:
            github.close()

    # ------------------------------------------------------------------
    # Block / unblock
    # ------------------------------------------------------------------

    def block_source(self, source_id: UUID) -> dict[str, Any]:
        """Block a source: it stops being indexed on the next sync."""
        row = self._require_source(source_id)
        row.admission_status = kb_admission.ADMISSION_BLOCKED
        row.updated_at = datetime.now(timezone.utc)
        # The approval record survives blocking; unblock restores it.
        self._log_event(row.id, rules.EVENT_BLOCKED, "Источник заблокирован", None)
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    def unblock_source(self, source_id: UUID) -> dict[str, Any]:
        """Unblock a source: restores the previous approved compositions if any,
        otherwise returns to pending (fail-closed)."""
        row = self._require_source(source_id)
        if row.approved_preview_id is not None:
            row.admission_status = kb_admission.ADMISSION_APPROVED
            summary = "Разблокирован: восстановлен прежний одобренный состав"
        else:
            row.admission_status = kb_admission.ADMISSION_PENDING
            summary = "Разблокирован: возвращён в статус pending"
        row.updated_at = datetime.now(timezone.utc)
        self._log_event(row.id, rules.EVENT_UNBLOCKED, summary, None)
        self._db.commit()
        self._db.refresh(row)
        return self._source_to_dict(row)

    # ------------------------------------------------------------------
    # Decision history
    # ------------------------------------------------------------------

    def list_events(self, source_id: UUID, limit: int = 50) -> list[dict[str, Any]]:
        """Return admission decision history events for a source (newest first)."""
        self._require_source(source_id)
        rows = self._db.scalars(
            select(KBAdmissionEvent)
            .where(KBAdmissionEvent.source_id == source_id)
            .order_by(KBAdmissionEvent.created_at.desc())
            .limit(min(limit, 200))
        ).all()
        return [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "summary": r.summary,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_source(self, source_id: UUID) -> KnowledgeSource:
        row = self._db.get(KnowledgeSource, source_id)
        if not row:
            raise HTTPException(404, "Knowledge source not found")
        return row

    def _log_event(
        self,
        source_id: UUID,
        event_type: str,
        summary: str,
        details: Any,
    ) -> None:
        self._db.add(
            KBAdmissionEvent(
                id=uuid4(),
                source_id=source_id,
                event_type=event_type,
                summary=summary,
                details=details,
            )
        )