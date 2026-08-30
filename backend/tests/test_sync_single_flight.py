"""
Tests for the manual KB sync single-flight guard (owner decision
29.08.2026, variant "A"): only one sync job may be 'running'; a job stuck
past the staleness window is a restart zombie and is closed so syncs
unblock; the partial unique index (migration 019) is the last line —
IntegrityError from two simultaneous POSTs maps to the same 409.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.admin.knowledge_base_service import KnowledgeBaseService


def test_start_sync_job_rejects_while_fresh_running():
    running = SimpleNamespace(
        id="j1", status="running",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = running
    service = KnowledgeBaseService(db)
    with pytest.raises(Exception) as excinfo:
        service.start_sync_job()
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "sync_already_running"
    db.add.assert_not_called()


def test_start_sync_job_closes_stale_zombie_and_proceeds():
    zombie = SimpleNamespace(
        id="j2", status="running",
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        error_message=None, finished_at=None,
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = zombie
    service = KnowledgeBaseService(db)
    service.start_sync_job()
    assert zombie.status == "error"
    assert "single-flight" in (zombie.error_message or "")
    db.add.assert_called_once()
    db.commit.assert_called()


def test_start_sync_job_integrity_error_maps_to_409():
    """Two simultaneous POSTs: the partial unique index (019) is the last
    line of defense — IntegrityError becomes the same clean 409."""
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    db.commit.side_effect = IntegrityError("dup", None, Exception())
    service = KnowledgeBaseService(db)
    with pytest.raises(Exception) as excinfo:
        service.start_sync_job()
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "sync_already_running"
    db.rollback.assert_called_once()


def test_get_running_job_returns_none_or_job():
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    assert KnowledgeBaseService(db).get_running_job() is None
    db.scalars.return_value.first.return_value = SimpleNamespace(
        id="j3", status="running", started_at=None, finished_at=None,
        stats={}, error_message=None,
    )
    assert KnowledgeBaseService(db).get_running_job() is not None