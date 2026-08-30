"""
Tests for the registry-only KB policy binding (owner decision 29.08.2026,
model "A"): a knowledge source MUST be bound to an existing registry card
at the point of entry (KnowledgeBaseService.create_source), and its caption
defaults to the card title.

Condition 3 (variant В2): a github_repo source must live in the owner's
namespace (KB_REPO_OWNER, required per-deployment setting — no personal
values in code) and must actually exist on GitHub (live probe, tri-state:
True/False/None — None means "GitHub unreachable" and fails closed).

DB-level enforcement (FK NOT NULL + ON DELETE RESTRICT) lives in migration
016 and is validated against a production DB copy; these tests cover the
request-level guard with a mocked session (same pattern as
test_sync_delete_guard.py). The probe is monkeypatched — no real network.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.admin.knowledge_base_service import KnowledgeBaseService

ALLOWED_OWNER = "allowed-owner"


@pytest.fixture(autouse=True)
def _owner_namespace(monkeypatch):
    """
    KB_REPO_OWNER — обязательная настройка экземпляра; на хосте она несёт
    реальное значение из .env, а happy-path тесты используют ALLOWED_OWNER.
    Фикстура фиксирует namespace для всего модуля и чистит кеш настроек
    до и после каждого теста (иначе порядок прогонов делает тесты
    зависимыми от чужого monkeypatch).
    """
    from app.core.config import get_settings
    monkeypatch.setenv("KB_REPO_OWNER", ALLOWED_OWNER)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _service(card):
    db = MagicMock()
    db.get.return_value = card
    db.scalars.return_value.first.return_value = None  # no duplicate identifier
    service = KnowledgeBaseService(db)
    # Happy-path probe: repo exists. Individual tests override as needed.
    service._probe_repo = lambda owner, repo: True
    return service, db


def test_create_source_without_card_rejected():
    """POST without an existing registry card → 409 project_not_in_registry."""
    service, db = _service(card=None)
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": f"{ALLOWED_OWNER}/telegram-ai-gateway",
            "project_card_id": "00000000-0000-0000-0000-000000000000",
        })
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "project_not_in_registry"
    # Fail-closed on the entry point: nothing may be inserted.
    db.add.assert_not_called()


def test_create_source_without_card_id_rejected():
    """Missing project_card_id is treated as unbound, not as a wildcard."""
    service, db = _service(card=None)
    with pytest.raises(Exception):
        service.create_source({"source_type": "github_repo", "identifier": "x/y"})
    db.add.assert_not_called()
    # Rejection must happen before any card lookup when no id is given.
    db.get.assert_not_called()


def test_create_source_card_checked_before_identifier_allowance():
    """Order: the binding guard fires even for a foreign-repo identifier —
    card existence is condition 1 and is judged first."""
    service, db = _service(card=None)
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": "facebook/react",
            "project_card_id": "00000000-0000-0000-0000-000000000000",
        })
    assert excinfo.value.detail["reason_code"] == "project_not_in_registry"
    db.add.assert_not_called()


def test_create_source_binds_card_and_defaults_caption_from_card():
    """Bound source: project_card_id = card id, caption = card title."""
    card = SimpleNamespace(id="0c0ffe-1", title="Telegram AI Gateway")
    service, db = _service(card=card)
    created = service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/telegram-ai-gateway",
        "project_card_id": "0c0ffe-1",
    })
    row = db.add.call_args[0][0]
    assert str(row.project_card_id) == "0c0ffe-1"
    assert row.display_name == "Telegram AI Gateway"
    assert created is not None  # serialized source dict


def test_explicit_display_name_overrides_card_title():
    card = SimpleNamespace(id="0c0ffe-2", title="Telegram AI Gateway")
    service, db = _service(card=card)
    service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/telegram-ai-gateway",
        "project_card_id": "0c0ffe-2",
        "display_name": "TAIG",
    })
    row = db.add.call_args[0][0]
    assert row.display_name == "TAIG"


def test_create_source_duplicate_identifier_rejected():
    """One repository = one source (29.08, variant 1): duplicate → 409."""
    existing = SimpleNamespace(
        id="aaa", identifier=f"{ALLOWED_OWNER}/PromptReview", display_name="Prompt Review"
    )
    card = SimpleNamespace(id="0c0ffe-3", title="Prompt Review")
    db = MagicMock()
    db.get.return_value = card
    db.scalars.return_value.first.return_value = existing
    service = KnowledgeBaseService(db)
    service._probe_repo = lambda owner, repo: True
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": f"{ALLOWED_OWNER}/PromptReview",
            "project_card_id": "0c0ffe-3",
        })
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "source_already_exists"
    db.add.assert_not_called()


def test_create_source_fresh_identifier_proceeds_to_insert():
    """Fresh identifier → the row is built and handed to the session."""
    card = SimpleNamespace(id="0c0ffe-4", title="Telegram AI Gateway")
    db = MagicMock()
    db.get.return_value = card
    db.scalars.return_value.first.return_value = None
    service = KnowledgeBaseService(db)
    service._probe_repo = lambda owner, repo: True
    service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/telegram-ai-gateway",
        "project_card_id": "0c0ffe-4",
    })
    row = db.add.call_args[0][0]
    assert row.identifier == f"{ALLOWED_OWNER}/telegram-ai-gateway"


# --- Condition 3, variant В2: namespace + live probe -----------------------


def test_create_source_invalid_identifier_rejected():
    """Identifier without the owner/repo shape → 409 invalid_identifier."""
    card = SimpleNamespace(id="0c0ffe-5", title="Telegram AI Gateway")
    service, db = _service(card=card)
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": "just-a-repo-name",
            "project_card_id": "0c0ffe-5",
        })
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "invalid_identifier"
    db.add.assert_not_called()


def test_create_source_foreign_namespace_rejected(monkeypatch):
    """Foreign owner → 409 repo_not_owned: a repository by itself is no KB ticket."""
    monkeypatch.setenv("KB_REPO_OWNER", ALLOWED_OWNER)
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        card = SimpleNamespace(id="0c0ffe-6", title="Telegram AI Gateway")
        service, db = _service(card=card)
        with pytest.raises(Exception) as excinfo:
            service.create_source({
                "source_type": "github_repo",
                "identifier": "facebook/react",
                "project_card_id": "0c0ffe-6",
            })
        err = excinfo.value
        assert err.status_code == 409
        assert err.detail["reason_code"] == "repo_not_owned"
        db.add.assert_not_called()
    finally:
        get_settings.cache_clear()


def test_create_source_missing_repo_rejected():
    """Live probe says 404 → 409 repo_not_found."""
    card = SimpleNamespace(id="0c0ffe-7", title="Telegram AI Gateway")
    service, db = _service(card=card)
    service._probe_repo = lambda owner, repo: False
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": f"{ALLOWED_OWNER}/nonexistent-repo",
            "project_card_id": "0c0ffe-7",
        })
    err = excinfo.value
    assert err.status_code == 409
    assert err.detail["reason_code"] == "repo_not_found"
    db.add.assert_not_called()


def test_create_source_github_unavailable_fails_closed():
    """Live probe None (GitHub unreachable) → 503, nothing created."""
    card = SimpleNamespace(id="0c0ffe-8", title="Telegram AI Gateway")
    service, db = _service(card=card)
    service._probe_repo = lambda owner, repo: None
    with pytest.raises(Exception) as excinfo:
        service.create_source({
            "source_type": "github_repo",
            "identifier": f"{ALLOWED_OWNER}/telegram-ai-gateway",
            "project_card_id": "0c0ffe-8",
        })
    err = excinfo.value
    assert err.status_code == 503
    assert err.detail["reason_code"] == "repo_check_unavailable"
    db.add.assert_not_called()


def test_list_owner_repos_flags_connected_and_owner(monkeypatch):
    """Repo select payload: owner from settings, connected flag from DB."""
    monkeypatch.setenv("KB_REPO_OWNER", ALLOWED_OWNER)
    from app.core.config import get_settings
    get_settings.cache_clear()
    try:
        db = MagicMock()
        db.scalars.return_value.all.return_value = [f"{ALLOWED_OWNER}/one", f"{ALLOWED_OWNER}/two"]
        service = KnowledgeBaseService(db)
        service._fetch_owner_repos = lambda owner: [
            {"identifier": f"{owner}/one", "name": "one", "description": None,
             "updated_at": None, "archived": False},
            {"identifier": f"{owner}/three", "name": "three", "description": None,
             "updated_at": None, "archived": False},
        ]
        result = service.list_owner_repos()
        assert result["owner"] == ALLOWED_OWNER
        flags = {r["identifier"]: r["connected"] for r in result["repos"]}
        assert flags[f"{ALLOWED_OWNER}/one"] is True
        assert flags[f"{ALLOWED_OWNER}/three"] is False
    finally:
        get_settings.cache_clear()


def test_list_owner_repos_fails_closed_when_github_unreachable():
    """GitHub unreachable → 503 repo_list_unavailable, not an empty list."""
    db = MagicMock()
    service = KnowledgeBaseService(db)
    service._fetch_owner_repos = lambda owner: None
    with pytest.raises(Exception) as excinfo:
        service.list_owner_repos()
    err = excinfo.value
    assert err.status_code == 503
    assert err.detail["reason_code"] == "repo_list_unavailable"


def test_github_service_list_owner_repos_parses_payload():
    """Parsing: identifier built from owner+name; entries without name skipped."""
    from app.services.admin.github_knowledge_source_service import GitHubKnowledgeSourceService
    gh = GitHubKnowledgeSourceService(MagicMock())
    response = SimpleNamespace(
        status_code=200,
        json=lambda: [
            {"name": "repo-a", "description": "d", "updated_at": "2026-08-29", "archived": False},
            {"name": "", "archived": False},
            {"name": "repo-b", "description": None, "updated_at": None, "archived": True},
        ],
    )
    gh._client = MagicMock()
    gh._client.get.return_value = response
    try:
        repos = gh.list_owner_repos(ALLOWED_OWNER)
    finally:
        gh.close()
    assert [r["identifier"] for r in repos] == [
        f"{ALLOWED_OWNER}/repo-a",
        f"{ALLOWED_OWNER}/repo-b",
    ]
    assert repos[1]["archived"] is True


def test_card_delete_restricted_by_fk():
    """RESTRICT (migration 016): card with live sources cannot be deleted."""
    from app.models.entities import KnowledgeSource
    fk = [f for f in KnowledgeSource.__table__.foreign_keys
          if f.column.table.name == "project_cards"]
    assert len(fk) == 1, "KnowledgeSource must reference project_cards"
    assert fk[0].constraint.ondelete == "RESTRICT"

# ---------- Ветка источника: авто-детект дефолтной ветки ----------

def test_create_source_resolves_main_placeholder_to_default_branch():
    """UI префилл branch='main' + репозиторий на master → берём default_branch репо.

    Симптом-источник: 422 /commits/main при построении состава допуска
    (AI-Portfolio живёт на master)."""
    card = SimpleNamespace(id="0c0ffe-br1", title="AI Portfolio")
    service, db = _service(card=card)
    service._probe_repo = lambda owner, repo: True
    service._probe_default_branch = lambda owner, repo: "master"
    created = service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/AI-Portfolio",
        "project_card_id": "0c0ffe-br1",
        "branch": "main",
    })
    assert created["branch"] == "master"
    assert db.add.call_args[0][0].branch == "master"
    print("PASS: branch 'main' placeholder resolved to repo default branch")


def test_create_source_respects_explicit_branch():
    """Ветка, выбранная пользователем явным образом, детектом не перезаписывается."""
    card = SimpleNamespace(id="0c0ffe-br2", title="Some Project")
    service, db = _service(card=card)
    service._probe_repo = lambda owner, repo: True
    service._probe_default_branch = lambda owner, repo: "master"
    created = service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/some-repo",
        "project_card_id": "0c0ffe-br2",
        "branch": "dev",
    })
    assert created["branch"] == "dev"
    print("PASS: explicit branch respected")


def test_create_source_without_branch_keeps_old_default():
    """Без branch в payload (прямой API-вызов) — прежнее значение 'main',
    детект не выполняется (контракт обратной совместимости)."""
    card = SimpleNamespace(id="0c0ffe-br3", title="Some Project")
    service, db = _service(card=card)
    service._probe_repo = lambda owner, repo: True
    probe_calls = []

    def _deny(owner, repo):
        probe_calls.append((owner, repo))
        return "master"

    service._probe_default_branch = _deny
    created = service.create_source({
        "source_type": "github_repo",
        "identifier": f"{ALLOWED_OWNER}/some-repo",
        "project_card_id": "0c0ffe-br3",
    })
    assert created["branch"] == "main"
    assert probe_calls == []
    print("PASS: no branch in payload keeps 'main', no probe")
