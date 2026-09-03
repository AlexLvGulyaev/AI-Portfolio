"""
Tests for Admission Console guards (§4.5а) — pure decision logic.

Covers the approval guard (409 reasons, mirrored by the UI disabled-state),
display-status derivation, and the draft vs effective pattern model.

These run with the full backend deps (chromadb etc.), i.e. inside the
backend container image; on the host only tests without the services
package import need to apply.
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.admin import kb_admission_console as rules
from app.services.admin import kb_admission


def _preview(**kwargs):
    defaults = dict(
        id=uuid.uuid4(),
        status="ready",
        commit_sha="abc1234",
        include_patterns=["docs/**", "README.md"],
        exclude_patterns=["task_history/**"],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _source(**kwargs):
    defaults = dict(
        admission_status="pending",
        include_patterns=["docs/**", "README.md"],
        exclude_patterns=["task_history/**"],
        draft_include_patterns=None,
        draft_exclude_patterns=None,
        approved_preview_id=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ----------------------------------------------------------------------
# Approval guard
# ----------------------------------------------------------------------


def test_approval_without_preview_rejected():
    guard = rules.evaluate_approval("pending", None, ([], []), ([], []), "abc1234", None)
    assert not guard.allowed
    assert guard.reason_code == rules.APPROVAL_NO_PREVIEW


def test_approval_with_error_preview_rejected():
    guard = rules.evaluate_approval(
        "pending",
        _preview(status="error", error_message="discovery failed"),
        ([], []),
        ([], []),
        "abc1234",
        None,
    )
    assert guard.reason_code == rules.APPROVAL_PREVIEW_NOT_READY


def test_approval_with_changed_patterns_rejected():
    guard = rules.evaluate_approval(
        "pending",
        _preview(),
        (["docs/**", "README.md"], ["task_history/**"]),
        (["docs/**"], ["task_history/**"]),
        "abc1234",
        None,
    )
    assert guard.reason_code == rules.APPROVAL_PATTERNS_CHANGED


def test_approval_pattern_order_is_irrelevant():
    guard = rules.evaluate_approval(
        "pending",
        _preview(),
        (["docs/**", "README.md"], ["task_history/**"]),
        (["README.md", "docs/**"], ["task_history/**"]),
        "abc1234",
        None,
    )
    assert guard.allowed


def test_approval_with_new_head_commit_rejected():
    guard = rules.evaluate_approval(
        "pending",
        _preview(commit_sha="abc1234"),
        (["docs/**"], []),
        (["docs/**"], []),
        "def5678",
        None,
    )
    assert guard.reason_code == rules.APPROVAL_COMMIT_CHANGED


def test_approval_with_unknown_head_is_not_stale():
    """GitHub unreachable: fail-safe — the approval decision is made by the
    approved composition's own preview, not vetoed on a missing check."""
    guard = rules.evaluate_approval(
        "pending",
        _preview(commit_sha="abc1234"),
        (["docs/**"], []),
        (["docs/**"], []),
        None,
        None,
    )
    assert guard.allowed


def test_double_approval_rejected():
    preview = _preview()
    guard = rules.evaluate_approval(
        "approved",
        preview,
        (["docs/**", "README.md"], ["task_history/**"]),
        (["docs/**", "README.md"], ["task_history/**"]),
        "abc1234",
        preview.id,
    )
    assert guard.reason_code == rules.APPROVAL_ALREADY_APPROVED


def test_blocked_source_rejected():
    guard = rules.evaluate_approval(
        "blocked",
        _preview(),
        (["docs/**"], []),
        (["docs/**"], []),
        "abc1234",
        None,
    )
    assert guard.reason_code == rules.APPROVAL_SOURCE_BLOCKED


def test_approval_happy_path():
    guard = rules.evaluate_approval(
        "pending",
        _preview(),
        (["docs/**", "README.md"], ["task_history/**"]),
        (["docs/**", "README.md"], ["task_history/**"]),
        "abc1234",
        None,
    )
    assert guard.allowed and guard.reason_code is None


def test_unknown_status_fails_closed():
    guard = rules.evaluate_approval("weird", _preview(), ([], []), ([], []), "abc", None)
    assert not guard.allowed


# ----------------------------------------------------------------------
# Display status derivation (pure, no network)
# ----------------------------------------------------------------------


def test_display_status_blocked_has_priority():
    assert rules.derive_display_status("blocked", None, _source(admission_status="blocked")) == rules.STATUS_BLOCKED


def test_display_status_need_preview_when_no_preview():
    assert rules.derive_display_status("pending", None, _source()) == rules.STATUS_NEED_PREVIEW


def test_display_status_approved_with_clean_draft():
    status = rules.derive_display_status("approved", _preview(), _source(admission_status="approved"))
    assert status == rules.STATUS_APPROVED


def test_display_status_patterns_changed_after_approval():
    status = rules.derive_display_status(
        "approved",
        _preview(),
        _source(admission_status="approved", draft_include_patterns=["docs/**"]),
    )
    assert status == rules.STATUS_PATTERNS_CHANGED


def test_display_status_approved_with_identical_draft():
    # «Обновить состав» без изменения списков: идентичный черновик не
    # меняет статус одобренного источника (репорт владельца 03.09.2026).
    status = rules.derive_display_status(
        "approved",
        _preview(),
        _source(
            admission_status="approved",
            draft_include_patterns=["docs/**", "README.md"],
            draft_exclude_patterns=["task_history/**"],
        ),
    )
    assert status == rules.STATUS_APPROVED


def test_display_status_error():
    status = rules.derive_display_status(
        "pending", _preview(status="error"), _source()
    )
    assert status == rules.STATUS_ERROR


def test_display_status_preview_ready():
    status = rules.derive_display_status("pending", _preview(), _source())
    assert status == rules.STATUS_PREVIEW_READY


def test_display_status_patterns_changed_with_dirty_draft():
    status = rules.derive_display_status(
        "pending",
        _preview(),
        _source(draft_include_patterns=["docs/**"]),
    )
    assert status == rules.STATUS_PATTERNS_CHANGED


def test_display_status_need_preview_when_preview_older_than_draft():
    preview = _preview(include_patterns=["README.md"])
    status = rules.derive_display_status("pending", preview, _source())
    assert status == rules.STATUS_NEED_PREVIEW


# ----------------------------------------------------------------------
# Draft model helpers
# ----------------------------------------------------------------------


def test_draft_patterns_fall_back_to_effective():
    source = _source()
    include, exclude = rules.draft_patterns(source)
    assert include == ["docs/**", "README.md"]
    assert exclude == ["task_history/**"]


def test_draft_patterns_use_draft_columns_when_set():
    source = _source(draft_include_patterns=["docs/**"], draft_exclude_patterns=None)
    include, exclude = rules.draft_patterns(source)
    assert include == ["docs/**"]
    assert exclude == ["task_history/**"]


def test_has_draft_changes_for_approved_source():
    # Presence of a draft is not a change (fix 03.09.2026: «Обновить
    # состав» writes an identical draft and the source got stuck in
    # patterns_changed forever). Values are compared, same as for a
    # never-approved source.
    assert rules.has_draft_changes(_source(admission_status="approved")) is False
    assert rules.has_draft_changes(
        _source(
            admission_status="approved",
            draft_include_patterns=["docs/**", "README.md"],
        )
    ) is False
    assert rules.has_draft_changes(
        _source(admission_status="approved", draft_include_patterns=["x/**"])
    ) is True


def test_has_draft_changes_pending_with_same_value():
    # For a never-approved source a draft equal to the effective columns
    # is NOT a change: any fresh preview cycle is expressed via
    # need_preview, not patterns_changed.
    source = _source(draft_include_patterns=["docs/**", "README.md"])
    assert rules.has_draft_changes(source) is False
    assert (
        rules.has_draft_changes(_source(draft_include_patterns=["changed/**"]))
        is True
    )


def test_empty_whitelist_never_admits_via_gate():
    """Cross-check with the admission gate: empty include never indexes."""
    decisions = kb_admission.select_files(
        ["docs/x.md"], kb_admission.ADMISSION_APPROVED, [], []
    )
    assert decisions[0].reason == kb_admission.REASON_EMPTY_ALLOWLIST