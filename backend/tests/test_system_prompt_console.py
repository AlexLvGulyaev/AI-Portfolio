"""
Unit-тесты управляемого хранилища системного промпта (task 2026-08-30):

- validate_body: обязательные плейсхолдеры сборки + пробный .format;
- create_version: дедупликация по body_hash, активация с единственным is_active;
- activate/reset: переактивация существующих версий;
- load_active_prompt: fail-open (нет строки / ошибка БД → вшитый дефолт).

Сессия БД мокается (конвенция suite — без живой БД и TestClient).
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.entities import SystemPrompt
from app.services.admin.system_prompt_service import (
    body_hash,
    load_active_prompt,
    validate_body,
    SystemPromptService,
)

VALID_BODY = (
    "Правила. Реестр: {registry_block}\n{registry_list}\n"
    "Документы: {rag_context}\nИстория: {conversation_history}\n"
    "Вопрос: {user_query}\nОтвет:"
)


# ---------- validate_body ----------

def test_validate_body_requires_placeholders():
    errors = validate_body("ПРОМПТ БЕЗ ПЛЕЙСХОЛДЕРОВ")
    assert any("user_query" in e for e in errors), errors
    assert len(errors) == 5, errors
    print("PASS: body without placeholders rejected (one error per placeholder)")


def test_validate_body_accepts_full_template():
    assert validate_body(VALID_BODY) == []
    print("PASS: valid template passes")


def test_validate_body_rejects_broken_template():
    errors = validate_body(VALID_BODY + "\n{unexpected_placeholder}")
    # {unexpected_placeholder} ловится пробным .format
    assert any("не собирается" in e for e in errors), errors
    print("PASS: broken template flagged by .format probe")


# ---------- create_version ----------

def _fake_db():
    db = MagicMock()
    db.scalar.return_value = None  # нет дубликата по hash
    return db


def test_create_version_adds_and_activates():
    db = _fake_db()
    service = SystemPromptService(db)
    result = service.create_version("v5-owner", VALID_BODY, note="проверка")
    db.add.assert_called_once()
    row = db.add.call_args[0][0]
    assert isinstance(row, SystemPrompt)
    assert row.version == "v5-owner" and row.body == VALID_BODY
    assert row.body_hash == body_hash(VALID_BODY)
    # активация сбрасывает чужие is_active и выставляет свою
    db.execute.assert_called_once()
    db.commit.assert_called_once()
    assert row.is_active is True
    assert result == service._to_dict(row)
    print("PASS: create_version saves and activates")


def test_create_version_dedup_same_label_and_body():
    """Дедуп по паре (метка, тело): то же тело под той же меткой — переактивация."""
    db = _fake_db()
    existing = SystemPrompt(version="v6-again", body=VALID_BODY, body_hash=body_hash(VALID_BODY))
    existing.id = uuid.uuid4()
    db.scalar.return_value = existing
    service = SystemPromptService(db)
    result = service.create_version("v6-again", VALID_BODY)
    db.add.assert_not_called()  # новой строки нет — переактивация существующей
    db.get.assert_not_called()  # и не через activate(id) — напрямую _activate_row
    assert result["id"] == str(existing.id)
    print("PASS: same label+body reactivates existing row (no new row)")


def test_create_version_same_body_new_label_makes_new_row():
    """Решение владельца 30.08.2026: то же тело под новой меткой — отдельная запись."""
    db = _fake_db()
    db.scalar.return_value = None  # (метка v5, hash) не найдена
    existing = SystemPrompt(version="v4-compact-multi", body=VALID_BODY, body_hash=body_hash(VALID_BODY))
    existing.id = uuid.uuid4()
    service = SystemPromptService(db)
    result = service.create_version("v5", VALID_BODY)
    db.add.assert_called_once()  # новая строка создана
    row = db.add.call_args[0][0]
    assert row.version == "v5" and row.body_hash == body_hash(VALID_BODY)
    assert row.body == VALID_BODY
    assert result == service._to_dict(row)
    print("PASS: same body under new label creates a separate version row")


def test_create_version_invalid_body_rejected():
    service = SystemPromptService(_fake_db())
    try:
        service.create_version("v7", "нет плейсхолдеров")
        raise AssertionError("ValueError expected")
    except ValueError as exc:
        assert "плейсхолдер" in str(exc)
    print("PASS: invalid body rejected with 422-able ValueError")


def test_activate_switches_active_version():
    db = _fake_db()
    old = SystemPrompt(version="v4", body=SYSTEM_PROMPT_BODY, body_hash=body_hash(SYSTEM_PROMPT_BODY))
    db.get.return_value = old
    service = SystemPromptService(db)
    result = service.activate(uuid.uuid4())
    db.get.assert_called_once()
    assert result["version"] == "v4"
    print("PASS: activate re-enables existing version")


SYSTEM_PROMPT_BODY = "Т {registry_block} {registry_list} {rag_context} {conversation_history} {user_query}"


def test_activate_unknown_id_raises_lookup():
    db = _fake_db()
    db.get.return_value = None
    service = SystemPromptService(db)
    try:
        service.activate(uuid.uuid4())
        raise AssertionError("LookupError expected")
    except LookupError as exc:
        assert "system_prompt_not_found" in str(exc)
    print("PASS: unknown id -> LookupError (404 in API layer)")


def test_reset_to_builtin_creates_builtin_version():
    db = _fake_db()
    service = SystemPromptService(db)
    service.reset_to_builtin()
    row = db.add.call_args[0][0]
    assert row.is_builtin is True
    assert row.is_active is True
    print("PASS: reset activates builtin v4-compact-multi as managed row")


# ---------- load_active_prompt ----------

def test_load_active_prompt_returns_row():
    db = MagicMock()
    row = SimpleNamespace(body="УПРАВЛЯЕМЫЙ {registry_block} {registry_list} {rag_context} "
                                  "{conversation_history} {user_query}", version="v5-owner")
    db.scalar.return_value = row
    assert load_active_prompt(db) == (row.body, "v5-owner")
    print("PASS: active managed prompt loaded")


def test_load_active_prompt_no_row_falls_back():
    db = MagicMock()
    db.scalar.return_value = None
    assert load_active_prompt(db) == (None, None)
    print("PASS: no active row -> builtin default")


def test_load_active_prompt_db_error_fails_open():
    db = MagicMock()
    db.scalar.side_effect = RuntimeError("db down")
    assert load_active_prompt(db) == (None, None)
    print("PASS: db error -> fail-open to builtin default")


# ---------- orchestrator fingerprint ----------

def test_orchestrator_config_fingerprint_uses_managed_prompt():
    """Fingerprint конфигурации берётся из инстанса PromptAssembly."""
    from app.services.prompt_assembly import PromptAssembly

    class Mini:
        rag_service = SimpleNamespace(config=SimpleNamespace(collection_name="kb"))

    orch = Mini()
    orch.prompt_assembly = PromptAssembly()
    orch.rag_top_k = 6
    from app.services.chat_orchestrator import ChatOrchestrator
    import inspect
    src = inspect.getsource(ChatOrchestrator._config_fingerprint)
    assert "self.prompt_assembly.fingerprint()" in src
    print("PASS: config fingerprint sourced from managed prompt instance")


if __name__ == "__main__":
    import inspect
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL SYSTEM PROMPT TESTS PASSED")