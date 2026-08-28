"""
Tests for the delete-before-discovery fix in GitHubKnowledgeSourceService.

Incident (2026-08-28, KB admission campaign): sync wiped a source's
documents in PostgreSQL before discovery; when discovery failed (e.g.
GitHub rate limit), documents were lost while ChromaDB chunks — removed
only incrementally during re-indexing — survived. The fix makes
save_fetched_files fail-closed: on a discovery failure existing documents
are kept and only the errors are recorded.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.admin.github_knowledge_source_service import (
    GitHubFile,
    GitHubKnowledgeSourceService,
    has_discovery_failure,
)


def test_has_discovery_failure_detects_fatal_types():
    assert has_discovery_failure([
        {"path": "r", "error_type": "discovery_failed", "error_message": "403"}
    ])
    assert has_discovery_failure([
        {"path": "r", "error_type": "invalid_identifier", "error_message": "bad id"}
    ])
    assert has_discovery_failure([
        {"path": "r", "error_type": "invalid_source_type", "error_message": "bad type"}
    ])


def test_has_discovery_failure_ignores_per_file_errors():
    # fetch_failed for individual files means discovery succeeded.
    assert not has_discovery_failure([
        {"path": "docs/x.md", "error_type": "fetch_failed", "error_message": "404"}
    ])
    assert not has_discovery_failure([])


def _make_service() -> tuple[GitHubKnowledgeSourceService, MagicMock]:
    db = MagicMock()
    return GitHubKnowledgeSourceService(db), db


def test_save_keeps_documents_on_discovery_failure():
    svc, db = _make_service()
    svc.save_fetched_files(
        source_id=__import__("uuid").uuid4(),
        files=[],
        errors=[{"path": "r", "error_type": "discovery_failed", "error_message": "403"}],
    )
    # Old documents must NOT be deleted.
    db.query.assert_not_called()
    # The error is recorded and the change is committed.
    db.add.assert_called_once()
    db.commit.assert_called_once()
    print("PASS: discovery failure keeps existing documents")


def test_save_replaces_documents_on_successful_discovery():
    svc, db = _make_service()
    query = db.query.return_value
    query.filter.return_value.delete.return_value = 0
    svc.save_fetched_files(
        source_id=__import__("uuid").uuid4(),
        files=[GitHubFile(path="README.md", title=None, content="# t", raw_url="u")],
        errors=[],
    )
    db.query.assert_called_once()
    query.filter.return_value.delete.assert_called_once()
    db.add.assert_called_once()
    db.commit.assert_called_once()
    print("PASS: successful discovery replaces documents")


if __name__ == "__main__":
    test_has_discovery_failure_detects_fatal_types()
    test_has_discovery_failure_ignores_per_file_errors()
    print("PASS: has_discovery_failure contract")
    test_save_keeps_documents_on_discovery_failure()
    test_save_replaces_documents_on_successful_discovery()
    print("All delete-before-discovery tests passed.")