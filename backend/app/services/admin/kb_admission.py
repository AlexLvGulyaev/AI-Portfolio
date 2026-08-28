"""
KB admission gate — fail-closed selection of repository files for indexing.

Single selection mechanism shared by the admin admission-preview operation
and the real GitHub Sync ingestion. Pure functions only: no network, no DB,
no ChromaDB, no LLM classification.

Rules:
- only sources with admission_status == "approved" may be indexed;
- pending / blocked / unknown / invalid status never index;
- an empty include-pattern list never means "index everything";
- explicit include patterns are required to admit any file;
- exclude patterns take priority over include patterns;
- only file types supported by the current ingestion (Markdown) are eligible.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Iterable, Optional

ADMISSION_PENDING = "pending"
ADMISSION_APPROVED = "approved"
ADMISSION_BLOCKED = "blocked"
ADMISSION_STATUSES = (ADMISSION_PENDING, ADMISSION_APPROVED, ADMISSION_BLOCKED)

# File types supported by the current GitHub ingestion (see
# GitHubKnowledgeSourceService._discover_markdown_paths).
SUPPORTED_EXTENSIONS = (".md",)

REASON_UNSUPPORTED_TYPE = "unsupported_file_type"
REASON_SOURCE_NOT_APPROVED = "source_not_approved"
REASON_UNKNOWN_STATUS = "unknown_admission_status"
REASON_INVALID_INCLUDE = "invalid_include_patterns"
REASON_INVALID_EXCLUDE = "invalid_exclude_patterns"
REASON_EMPTY_ALLOWLIST = "empty_allowlist"
REASON_EXCLUDED_BY_PATTERN = "excluded_by_pattern"
REASON_NOT_MATCHED = "not_matched_by_include_patterns"
REASON_INCLUDED = "included"


@dataclass
class AdmissionDecision:
    """Selection decision for a single repository file."""

    path: str
    included: bool
    reason: str


def normalize_repo_path(path: Any) -> str:
    """Normalize a GitHub repository path to a canonical POSIX form."""
    if not isinstance(path, str):
        return ""
    value = path.replace("\\", "/")
    # Collapse duplicate slashes and drop current-directory segments.
    parts = [part for part in value.split("/") if part not in ("", ".")]
    return "/".join(parts)


def normalize_admission_status(value: Any) -> Optional[str]:
    """Return a known admission status, or None for unknown/invalid values.

    Strict: only exact canonical values are recognized; anything else is
    treated as unknown and fails closed.
    """
    if not isinstance(value, str):
        return None
    return value if value in ADMISSION_STATUSES else None


def normalize_patterns(value: Any) -> Optional[list[str]]:
    """Normalize a pattern list; None signals an invalid (fail-closed) value."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return None
    patterns: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        pattern = item.strip()
        if pattern:
            patterns.append(pattern)
    return patterns


def source_indexable(source: Any) -> tuple[bool, str]:
    """Source-level gate: may the sync pipeline process this source at all?"""
    status = normalize_admission_status(getattr(source, "admission_status", None))
    if status is None:
        return False, f"{REASON_UNKNOWN_STATUS}: {getattr(source, 'admission_status', None)!r}"
    if status == ADMISSION_BLOCKED:
        return False, f"{REASON_SOURCE_NOT_APPROVED}: blocked"
    if status == ADMISSION_PENDING:
        return False, f"{REASON_SOURCE_NOT_APPROVED}: pending"
    return True, "approved"


def decide_file(
    path: Any,
    admission_status: Any,
    include_patterns: Any,
    exclude_patterns: Any,
) -> AdmissionDecision:
    """Decide whether a single repository file may be indexed."""
    normalized = normalize_repo_path(path)

    if not normalized.lower().endswith(SUPPORTED_EXTENSIONS):
        return AdmissionDecision(normalized, False, REASON_UNSUPPORTED_TYPE)

    status = normalize_admission_status(admission_status)
    if status is None:
        return AdmissionDecision(normalized, False, f"{REASON_UNKNOWN_STATUS}: {admission_status!r}")
    if status != ADMISSION_APPROVED:
        return AdmissionDecision(normalized, False, f"{REASON_SOURCE_NOT_APPROVED}: {status}")

    includes = normalize_patterns(include_patterns)
    if includes is None:
        return AdmissionDecision(normalized, False, REASON_INVALID_INCLUDE)

    excludes = normalize_patterns(exclude_patterns)
    if excludes is None:
        return AdmissionDecision(normalized, False, REASON_INVALID_EXCLUDE)

    # Empty allowlist never opens the whole repository: explicit rules required.
    if not includes:
        return AdmissionDecision(normalized, False, REASON_EMPTY_ALLOWLIST)

    # Exclude patterns take priority over include patterns.
    for pattern in excludes:
        if _match(pattern, normalized):
            return AdmissionDecision(normalized, False, f"{REASON_EXCLUDED_BY_PATTERN}: {pattern}")

    for pattern in includes:
        if _match(pattern, normalized):
            return AdmissionDecision(normalized, True, f"{REASON_INCLUDED}: {pattern}")

    return AdmissionDecision(normalized, False, REASON_NOT_MATCHED)


def select_files(
    paths: Iterable[Any],
    admission_status: Any,
    include_patterns: Any,
    exclude_patterns: Any,
) -> list[AdmissionDecision]:
    """Apply the admission gate to a list of repository file paths."""
    return [
        decide_file(path, admission_status, include_patterns, exclude_patterns)
        for path in paths
    ]


def _match(pattern: str, normalized_path: str) -> bool:
    """Match a normalized repository path against a glob pattern."""
    if fnmatch.fnmatch(normalized_path, pattern):
        return True
    # A trailing-slash or directory pattern ("docs", "docs/") admits the
    # whole subtree, mirroring common .gitignore semantics.
    if fnmatch.fnmatch(normalized_path, f"{pattern.rstrip('/')}/**"):
        return True
    return False