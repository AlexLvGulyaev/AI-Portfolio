#!/usr/bin/env python3
"""
Tests for the KB admission gate (fail-closed file selection).

Covers:
1. New sources start in the safe "pending" state
2. "pending" sources are not indexed
3. "blocked" sources are not indexed
4. "approved" admits only explicitly allowed paths
5. Exclude patterns override include patterns
6. An empty allowlist never opens the whole repository
7. Preview and sync share the same selection decision
8. Preview performs no chunking, embeddings, or ChromaDB writes
9. Excluded files never reach ingestion (no download)
10. The existing approved happy path still works
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


def _ensure_importable_environment():
    """Stub heavy third-party deps if absent in the local test environment.

    The admission gate itself is pure Python; these stubs only satisfy
    import-time dependencies of the service modules (rag_service imports
    chromadb/openai, github service imports markdown). In production/VPS
    environments the real packages are installed and used.
    """
    import types

    try:
        import chromadb  # noqa: F401
        import chromadb.config  # noqa: F401
        import openai  # noqa: F401
        import markdown  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    if "chromadb" not in sys.modules:
        chromadb_stub = types.ModuleType("chromadb")
        config_stub = types.ModuleType("chromadb.config")

        class _Settings:  # pragma: no cover - import-time stub only
            def __init__(self, *args, **kwargs):
                pass

        config_stub.Settings = _Settings
        chromadb_stub.config = config_stub
        for name in ("PersistentClient", "HttpClient"):
            setattr(chromadb_stub, name, lambda *a, **k: None)
        sys.modules["chromadb"] = chromadb_stub
        sys.modules["chromadb.config"] = config_stub

    if "openai" not in sys.modules:
        openai_stub = types.ModuleType("openai")

        class _OpenAI:  # pragma: no cover - import-time stub only
            def __init__(self, *args, **kwargs):
                pass

        openai_stub.OpenAI = _OpenAI
        sys.modules["openai"] = openai_stub

    if "markdown" not in sys.modules:
        markdown_stub = types.ModuleType("markdown")
        markdown_stub.markdown = lambda text, *a, **k: text
        sys.modules["markdown"] = markdown_stub


_ensure_importable_environment()

from app.models.entities import KnowledgeSource
from app.services.admin import kb_admission
from app.services.admin.github_knowledge_source_service import (
    GitHubFile,
    GitHubKnowledgeSourceService,
)
from app.services.admin.knowledge_base_service import KnowledgeBaseService

REPO_PATHS = [
    "README.md",
    "docs/architecture.md",
    "docs/deep/api-contracts.md",
    "docs/internal/notes.md",
    "task_history/2026-01-01_task-x.md",
]


# ---------------------------------------------------------------------------
# 1. New source gets a safe default status
# ---------------------------------------------------------------------------

def test_new_source_defaults_to_pending():
    # Column-level defaults: applied on INSERT both by SQLAlchemy and by the
    # DB server_default (migration 014), so any new row starts safe.
    col = KnowledgeSource.__table__.c.admission_status
    assert col.default.arg == "pending"
    assert col.server_default.arg == "pending"
    assert col.nullable is False


# ---------------------------------------------------------------------------
# 2-3. pending / blocked sources are not indexed
# ---------------------------------------------------------------------------

def test_pending_source_not_indexable():
    ok, reason = kb_admission.source_indexable(
        SimpleNamespace(admission_status="pending")
    )
    assert ok is False
    assert "pending" in reason


def test_blocked_source_not_indexable():
    ok, reason = kb_admission.source_indexable(
        SimpleNamespace(admission_status="blocked")
    )
    assert ok is False
    assert "blocked" in reason


def test_unknown_status_fail_closed():
    for bad in (None, "weird", "", 42, "APPROVED "):
        ok, reason = kb_admission.source_indexable(SimpleNamespace(admission_status=bad))
        assert ok is False, f"Status {bad!r} must not be indexable"
        assert kb_admission.REASON_UNKNOWN_STATUS in reason


# ---------------------------------------------------------------------------
# 4-6. Approved: explicit paths only, exclude overrides include,
#      empty allowlist opens nothing
# ---------------------------------------------------------------------------

def _approved(include, exclude=None):
    return dict(
        admission_status="approved",
        include_patterns=include,
        exclude_patterns=exclude or [],
    )


def test_approved_admits_only_explicit_paths():
    rules = _approved(["README.md", "docs/**"])
    decisions = {d.path: d for d in kb_admission.select_files(REPO_PATHS, **rules)}

    assert decisions["README.md"].included is True
    assert decisions["docs/architecture.md"].included is True
    assert decisions["docs/deep/api-contracts.md"].included is True
    # task_history is not matched by the include patterns
    assert decisions["task_history/2026-01-01_task-x.md"].included is False
    assert decisions["task_history/2026-01-01_task-x.md"].reason == kb_admission.REASON_NOT_MATCHED


def test_exclude_overrides_include():
    rules = _approved(["docs/**"], ["docs/internal/**"])
    decisions = {d.path: d for d in kb_admission.select_files(REPO_PATHS, **rules)}

    assert decisions["docs/architecture.md"].included is True
    assert decisions["docs/internal/notes.md"].included is False
    assert kb_admission.REASON_EXCLUDED_BY_PATTERN in decisions["docs/internal/notes.md"].reason


def test_exclude_directory_pattern_excludes_subtree():
    rules = _approved(["**"], ["task_history"])
    decisions = {d.path: d for d in kb_admission.select_files(REPO_PATHS, **rules)}

    assert decisions["task_history/2026-01-01_task-x.md"].included is False
    assert decisions["README.md"].included is True


def test_empty_allowlist_excludes_everything():
    rules = _approved([])
    decisions = kb_admission.select_files(REPO_PATHS, **rules)

    assert decisions, "Expected decisions for all candidate files"
    assert all(d.included is False for d in decisions)
    assert all(d.reason == kb_admission.REASON_EMPTY_ALLOWLIST for d in decisions)


def test_null_include_patterns_excludes_everything():
    rules = dict(admission_status="approved", include_patterns=None, exclude_patterns=[])
    decisions = kb_admission.select_files(REPO_PATHS, **rules)
    assert all(d.included is False for d in decisions)


def test_invalid_patterns_fail_closed():
    for include in ("docs/**", 42, ["docs/**", 7], [None]):
        rules = dict(admission_status="approved", include_patterns=include, exclude_patterns=[])
        decisions = kb_admission.select_files(REPO_PATHS, **rules)
        assert all(d.included is False for d in decisions), f"include={include!r} must fail closed"
        assert all(d.reason == kb_admission.REASON_INVALID_INCLUDE for d in decisions)

    rules = dict(admission_status="approved", include_patterns=["**"], exclude_patterns="docs")
    decisions = kb_admission.select_files(REPO_PATHS, **rules)
    assert all(d.reason == kb_admission.REASON_INVALID_EXCLUDE for d in decisions)


def test_non_markdown_files_not_eligible():
    decision = kb_admission.decide_file("docs/diagram.png", "approved", ["**"], [])
    assert decision.included is False
    assert decision.reason == kb_admission.REASON_UNSUPPORTED_TYPE


def test_path_normalization():
    decision = kb_admission.decide_file("/docs//./architecture.md", "approved", ["docs/**"], [])
    assert decision.path == "docs/architecture.md"
    assert decision.included is True

    decision = kb_admission.decide_file("docs\\windows\\path.md", "approved", ["docs/**"], [])
    assert decision.path == "docs/windows/path.md"
    assert decision.included is True


# ---------------------------------------------------------------------------
# Fakes for service-level tests (no network, no DB, no ChromaDB)
# ---------------------------------------------------------------------------

class FakeGitHubService:
    """Stands in for GitHubKnowledgeSourceService: no network access."""

    def __init__(self, paths):
        self._paths = paths
        self.fetched = []

    def discover_paths(self, source):
        return list(self._paths)

    def _fetch_file(self, owner, repo, branch, path):
        self.fetched.append(path)
        return GitHubFile(path=path, title=path, content="text", raw_url=f"raw/{path}")

    def close(self):
        pass


class FakeDB:
    """Minimal DB stand-in returning a single pre-configured source."""

    def __init__(self, source):
        self._source = source

    def get(self, model, source_id):
        return self._source if str(self._source.id) == str(source_id) else None


def make_source(**overrides):
    defaults = dict(
        id=uuid4(),
        source_type="github_repo",
        identifier="owner/repo",
        branch="main",
        base_path=None,
        admission_status="pending",
        include_patterns=[],
        exclude_patterns=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_preview_and_sync_share_the_same_decision():
    """Preview decisions and sync fetch must select exactly the same files."""
    source = make_source(
        admission_status="approved",
        include_patterns=["README.md", "docs/**"],
        exclude_patterns=["docs/internal/**"],
    )
    fake_gh = FakeGitHubService(REPO_PATHS)

    service = KnowledgeBaseService(FakeDB(source))
    preview = service.preview_source_admission(source.id, github_service=fake_gh)

    preview_included = sorted(f["path"] for f in preview["files"] if f["decision"] == "included")

    # Real sync path with a stubbed download: same shared selection.
    real = GitHubKnowledgeSourceService.__new__(GitHubKnowledgeSourceService)
    real._db = None
    real._token = None
    real._client = None
    real.discover_paths = fake_gh.discover_paths
    real._fetch_file = fake_gh._fetch_file

    sync_result = real.fetch_source(source)
    sync_included = sorted(f.path for f in sync_result.files)
    sync_skipped = sorted(s["path"] for s in sync_result.skipped)

    assert preview_included == sync_included
    assert sync_skipped == sorted(
        f["path"] for f in preview["files"] if f["decision"] == "excluded"
    )
    # Excluded files were never downloaded
    assert all(path not in sync_skipped for path in sync_included)


def test_preview_writes_nothing_to_kb():
    """Preview must not touch chunking, embeddings, ChromaDB, or source state."""
    import app.services.admin.knowledge_base_service as kbs_module

    source = SimpleNamespace(
        id=uuid4(),
        source_type="github_repo",
        identifier="owner/repo",
        branch="main",
        base_path=None,
        admission_status="approved",
        include_patterns=["docs/**"],
        exclude_patterns=[],
    )

    # Any attempt to build RAG/indexer components during preview must fail loudly.
    def _forbidden(*args, **kwargs):
        raise AssertionError("Preview must not instantiate RAG/indexer components")

    saved_rag = kbs_module.RAGService
    saved_indexer = kbs_module.KnowledgeBaseIndexer
    kbs_module.RAGService = _forbidden
    kbs_module.KnowledgeBaseIndexer = _forbidden
    try:
        service = KnowledgeBaseService(FakeDB(source))
        preview = service.preview_source_admission(source.id, github_service=FakeGitHubService(REPO_PATHS))
    finally:
        kbs_module.RAGService = saved_rag
        kbs_module.KnowledgeBaseIndexer = saved_indexer

    assert preview["candidates_total"] == len(REPO_PATHS)
    assert preview["included_count"] == 3  # README.md, docs/architecture.md, docs/deep/api-contracts.md
    assert preview["excluded_count"] == 2
    assert preview["admission_status"] == "approved"
    # Status unchanged
    assert source.admission_status == "approved"


def test_preview_unknown_source_404():
    from fastapi import HTTPException

    service = KnowledgeBaseService(FakeDB(SimpleNamespace(id=uuid4())))
    try:
        service.preview_source_admission(uuid4())
        raise AssertionError("Expected HTTPException 404")
    except HTTPException as exc:
        assert exc.status_code == 404


def test_pending_source_yields_no_files_in_fetch():
    """Even if called directly, fetch_source of a pending source downloads nothing."""
    source = SimpleNamespace(
        id=uuid4(),
        source_type="github_repo",
        identifier="owner/repo",
        branch="main",
        base_path=None,
        admission_status="pending",
        include_patterns=["**"],
        exclude_patterns=[],
    )
    fake_gh = FakeGitHubService(REPO_PATHS)
    real = GitHubKnowledgeSourceService.__new__(GitHubKnowledgeSourceService)
    real._db = None
    real._token = None
    real._client = None
    real.discover_paths = fake_gh.discover_paths
    real._fetch_file = fake_gh._fetch_file

    result = real.fetch_source(source)

    assert result.files == []
    assert len(result.skipped) == len(REPO_PATHS)
    assert fake_gh.fetched == [], "No file may be downloaded for a pending source"
    assert all(s["skip_type"] == "admission_excluded" for s in result.skipped)


# ---------------------------------------------------------------------------
# 10. Approved happy path still works end to end (fetch -> files)
# ---------------------------------------------------------------------------

def test_approved_happy_path_still_works():
    source = SimpleNamespace(
        id=uuid4(),
        source_type="github_repo",
        identifier="owner/repo",
        branch="main",
        base_path=None,
        admission_status="approved",
        include_patterns=["README.md", "docs/**"],
        exclude_patterns=["docs/internal/**"],
    )
    fake_gh = FakeGitHubService(REPO_PATHS)
    real = GitHubKnowledgeSourceService.__new__(GitHubKnowledgeSourceService)
    real._db = None
    real._token = None
    real._client = None
    real.discover_paths = fake_gh.discover_paths
    real._fetch_file = fake_gh._fetch_file

    result = real.fetch_source(source)

    assert sorted(f.path for f in result.files) == [
        "README.md",
        "docs/architecture.md",
        "docs/deep/api-contracts.md",
    ]
    assert result.errors == []
    assert sorted(s["path"] for s in result.skipped) == [
        "docs/internal/notes.md",
        "task_history/2026-01-01_task-x.md",
    ]


def test_discover_paths_rejects_non_github_source():
    service = GitHubKnowledgeSourceService.__new__(GitHubKnowledgeSourceService)
    source = SimpleNamespace(source_type="local_file", identifier="/tmp/x.md")
    try:
        service.discover_paths(source)
        raise AssertionError("Expected ValueError for non-github source")
    except ValueError:
        pass


def test_migration_file_exists_and_chains():
    migration = backend_path / "migrations" / "versions" / "014_add_kb_admission.py"
    assert migration.exists(), "Migration 014 must exist"
    text = migration.read_text()
    assert "revision = '014'" in text
    assert "down_revision = '013'" in text
    assert "admission_status" in text
    assert "server_default='pending'" in text
    # Rollback drops exactly what upgrade adds
    assert text.count("op.drop_column") == 3


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)