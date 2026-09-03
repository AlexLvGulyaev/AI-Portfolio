"""
Admission Console logic — pure, testable decision helpers.

§4.5а: approval is the only action that changes the effective composition.
The guards below are evaluated both by the API (returning HTTP 409 with a
machine-readable reason) and implicitly by the disabled-state logic of the
console UI. Kept pure (no DB, no network) so the double protection is
trivially testable.

Draft patterns model:
- effective patterns: source.include_patterns / source.exclude_patterns —
  consumed by the sync pipeline; changed ONLY by approval;
- draft patterns: source.draft_* (None means "equal to effective");
- a preview is built from the draft patterns and is immutable afterwards.

Preview freshness (stale protection):
- patterns_stale: preview patterns differ from the current draft;
- commit_stale: the repository head commit differs from the preview's
  commit SHA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.admin import kb_admission

# Approval guard reason codes (HTTP 409 + machine-readable).
APPROVAL_NO_PREVIEW = "no_preview"
APPROVAL_PREVIEW_NOT_READY = "preview_not_ready"
APPROVAL_PATTERNS_CHANGED = "patterns_changed"
APPROVAL_COMMIT_CHANGED = "commit_changed"
APPROVAL_ALREADY_APPROVED = "already_approved"
APPROVAL_SOURCE_BLOCKED = "source_blocked"

# Console display statuses (derived server-side, no network).
STATUS_PATTERNS_CHANGED = "patterns_changed"
STATUS_ERROR = "error"
STATUS_BLOCKED = "blocked"
STATUS_APPROVED = "approved"
STATUS_PREVIEW_READY = "preview_ready"
STATUS_NEED_PREVIEW = "need_preview"

EVENT_SOURCE_CREATED = "created"
EVENT_PREVIEW_CREATED = "preview_created"
EVENT_PREVIEW_FAILED = "preview_failed"
EVENT_APPROVED = "approved"
EVENT_BLOCKED = "blocked"
EVENT_UNBLOCKED = "unblocked"
EVENT_DRAFT_UPDATED = "draft_updated"
EVENT_DRAFT_RESET = "draft_reset"
EVENT_APPROVAL_REJECTED = "approval_rejected"


@dataclass
class ApprovalGuard:
    """Result of approval-guard evaluation."""

    allowed: bool
    reason_code: Optional[str] = None
    message: Optional[str] = None


def draft_patterns(source: Any) -> tuple[Optional[list[str]], Optional[list[str]]]:
    """Return the draft pattern lists (draft columns if set, else effective)."""
    include = source.draft_include_patterns
    exclude = source.draft_exclude_patterns
    if include is None:
        include = source.include_patterns
    if exclude is None:
        exclude = source.exclude_patterns
    return include, exclude


def has_draft_changes(source: Any) -> bool:
    """True when the draft patterns differ from the effective patterns.

    Сравнение по значениям, не по факту наличия draft-колонок: «Обновить
    состав» пишет черновик даже при идентичных списках, и присутствие
    черновика само по себе не является изменением состава (иначе одобренный
    источник навсегда подвешивался в patterns_changed — репорт владельца
    03.09.2026).
    """
    if source.draft_include_patterns is None and source.draft_exclude_patterns is None:
        return False
    draft_inc, draft_exc = draft_patterns(source)
    return _patterns_differ(draft_inc, source.include_patterns) or _patterns_differ(draft_exc, source.exclude_patterns)


def _patterns_differ(a: Any, b: Any) -> bool:
    left = list(a or [])
    right = list(b or [])
    if sorted([p.strip() for p in left if p and str(p).strip()]) == sorted(
        [p.strip() for p in right if p and str(p).strip()]
    ):
        return False
    # Fall back to raw comparison when strip-normalized inputs differ only
    # in representation the admission gate would treat identically anyway.
    return sorted(map(str, left)) != sorted(map(str, right))


def evaluate_approval(
    admission_status: Any,
    latest_preview: Any,
    preview_patterns: tuple[list[str], list[str]],
    draft: tuple[Any, Any],
    current_head_sha: Optional[str],
    approved_preview_id: Any,
) -> ApprovalGuard:
    """Pure approval guard for §4.5а (mirrored 1:1 by the UI disabled-reasons).

    Params:
    - admission_status: source.admission_status;
    - latest_preview: latest KBAdmissionPreview row or None;
    - preview_patterns: (include, exclude) stored in that preview;
    - draft: (include, exclude) current draft pattern lists;
    - current_head_sha: repository head commit at approval time (None when
      GitHub could not be reached — treated as unknown, not stale);
    - approved_preview_id: source.approved_preview_id.
    """
    status = kb_admission.normalize_admission_status(admission_status)
    if status is None:
        return ApprovalGuard(False, APPROVAL_SOURCE_BLOCKED, "Unknown admission status")
    if status == kb_admission.ADMISSION_BLOCKED:
        return ApprovalGuard(False, APPROVAL_SOURCE_BLOCKED, "Источник заблокирован")

    if latest_preview is None:
        return ApprovalGuard(False, APPROVAL_NO_PREVIEW, "Preview не построен — сначала сформируйте preview")
    if getattr(latest_preview, "status", None) != "ready":
        return ApprovalGuard(
            False,
            APPROVAL_PREVIEW_NOT_READY,
            f"Последний preview завершился ошибкой: {getattr(latest_preview, 'error_message', '') or 'unknown'}",
        )

    if _preview_patterns_differ(preview_patterns, draft):
        return ApprovalGuard(False, APPROVAL_PATTERNS_CHANGED, "Паттерны изменились с момента построения preview")

    if current_head_sha and getattr(latest_preview, "commit_sha", None) and current_head_sha != latest_preview.commit_sha:
        return ApprovalGuard(
            False,
            APPROVAL_COMMIT_CHANGED,
            f"В репозитории новые коммиты (preview: {str(latest_preview.commit_sha)[:7]}, head: {str(current_head_sha)[:7]})",
        )

    if status == kb_admission.ADMISSION_APPROVED and approved_preview_id == getattr(latest_preview, "id", None):
        return ApprovalGuard(False, APPROVAL_ALREADY_APPROVED, "Этот состав уже одобрен")

    return ApprovalGuard(True)


def _preview_patterns_differ(preview_patterns: tuple[list[str], list[str]], draft: tuple[Any, Any]) -> bool:
    p_inc = [str(p) for p in (preview_patterns[0] or []) if p is not None]
    p_exc = [str(p) for p in (preview_patterns[1] or []) if p is not None]
    d_inc = [str(p) for p in (draft[0] or []) if p is not None]
    d_exc = [str(p) for p in (draft[1] or []) if p is not None]
    return sorted(p_inc) != sorted(d_inc) or sorted(p_exc) != sorted(d_exc)


def derive_display_status(
    admission_status: Any,
    latest_preview: Any,
    draft_source: Any,
) -> str:
    """Derive the console display status WITHOUT any network calls.

    Order: blocked > patterns_changed > error > preview_ready > approved >
    need_preview. Commit-level staleness is detected at preview-build time
    and at approval time (both networked), not here.
    """
    status = kb_admission.normalize_admission_status(admission_status)
    if status is None or status == kb_admission.ADMISSION_BLOCKED:
        return STATUS_BLOCKED

    if status == kb_admission.ADMISSION_APPROVED and not has_draft_changes(draft_source):
        # Approved with the effective composition still in force. If the
        # latest ready preview differs from the draft it is simply an older
        # artifact, not a decision-blocking state.
        if latest_preview is not None and getattr(latest_preview, "status", None) == "error":
            return STATUS_APPROVED
        return STATUS_APPROVED

    if latest_preview is None:
        draft_inc, _ = draft_patterns(draft_source)
        if not [p for p in (draft_inc or []) if p and str(p).strip()]:
            return STATUS_NEED_PREVIEW
        return STATUS_NEED_PREVIEW

    if getattr(latest_preview, "status", None) == "error":
        return STATUS_ERROR

    if has_draft_changes(draft_source):
        return STATUS_PATTERNS_CHANGED

    # Draft built a ready preview: is it still fresh relative to the draft?
    preview_patterns = (
        latest_preview.include_patterns or [],
        latest_preview.exclude_patterns or [],
    )
    if _preview_patterns_differ(preview_patterns, draft_patterns(draft_source)):
        return STATUS_NEED_PREVIEW

    return STATUS_PREVIEW_READY