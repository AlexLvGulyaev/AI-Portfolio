"""
Unit-тесты аудита админ-мутаций (task 2026-08-30, канон ai-curator):

- log_admin_action: event_type="admin_action", source="admin_console",
  query="action resource_type", metadata с changed_fields/ip/user_agent/path;
- fire-and-forget: ошибка логирования не ломает админ-действие;
- по одному инструментированному эндпойнту на модуль (kb, ai_config,
  retrieval_tuning, system_prompt) — аудит-строка создаётся после успешной
  мутации.

Сессия БД и Request мокаются (конвенция suite — без живой БД и TestClient).
"""

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _fake_request(path="/api/admin/x"):
    request = MagicMock()
    request.headers = {"user-agent": "pytest-agent"}
    request.url = SimpleNamespace(path=path)
    request.client = SimpleNamespace(host="10.0.0.5")
    return request


def _fake_forwarded_request(path="/api/admin/x"):
    request = _fake_request(path)
    request.headers = {
        "user-agent": "pytest-agent",
        "x-forwarded-for": "203.0.113.9, 10.0.0.1",
    }
    return request


# ---------- helper ----------

def test_log_admin_action_writes_canonical_event():
    from app.api.admin import audit as audit_mod

    db = MagicMock()
    svc = MagicMock()
    with patch.object(audit_mod, "OperationalLogService", return_value=svc):
        audit_mod.log_admin_action(
            _fake_request("/api/admin/knowledge-base/sources/e1/approve"),
            db,
            action="approve",
            resource_type="kb",
            resource_id=uuid.UUID("00000000-0000-0000-0000-0000000000e1"),
        )
    svc.log_event.assert_called_once()
    kwargs = svc.log_event.call_args.kwargs
    assert kwargs["event_type"] == "admin_action"
    assert kwargs["source"] == "admin_console"
    assert kwargs["query"] == "approve kb"
    assert kwargs["status"] == "ok"
    meta = kwargs["metadata"]
    assert meta["action"] == "approve"
    assert meta["resource_type"] == "kb"
    assert meta["resource_id"] == "00000000-0000-0000-0000-0000000000e1"
    assert meta["changed_fields"] == []
    assert meta["ip"] == "10.0.0.5"
    assert meta["user_agent"] == "pytest-agent"
    assert meta["path"] == "/api/admin/knowledge-base/sources/e1/approve"
    assert "details" not in meta
    print("PASS: log_admin_action writes canonical admin_action event")


def test_log_admin_action_client_ip_prefers_forwarded():
    from app.api.admin import audit as audit_mod

    meta_holder = {}

    class Svc:
        def log_event(self, **kw):
            meta_holder.update(kw["metadata"])

    with patch.object(audit_mod, "OperationalLogService", return_value=Svc()):
        audit_mod.log_admin_action(
            _fake_forwarded_request(), MagicMock(), action="update", resource_type="ai_config"
        )
    assert meta_holder["ip"] == "203.0.113.9"
    print("PASS: client ip prefers x-forwarded-for first hop")


def test_log_admin_action_changed_fields_and_details():
    from app.api.admin import audit as audit_mod

    svc = MagicMock()
    db = MagicMock()
    with patch.object(audit_mod, "OperationalLogService", return_value=svc):
        audit_mod.log_admin_action(
            _fake_request(), db, action="update", resource_type="retrieval_tuning",
            changed_fields=["rag_top_k", "rag_max_distance"],
            details={"resync_required": False},
        )
    meta = svc.log_event.call_args.kwargs["metadata"]
    assert meta["changed_fields"] == ["rag_top_k", "rag_max_distance"]
    assert meta["details"] == {"resync_required": False}
    print("PASS: changed_fields and details land in metadata")


def test_log_admin_action_never_breaks_action():
    from app.api.admin import audit as audit_mod

    svc = MagicMock()
    svc.log_event.side_effect = RuntimeError("audit db down")
    with patch.object(audit_mod, "OperationalLogService", return_value=svc):
        # не должно рейзить — fire-and-forget (canon ai-curator)
        audit_mod.log_admin_action(
            _fake_request(), MagicMock(), action="cache_clear", resource_type="retrieval_tuning"
        )
    print("PASS: audit failure swallowed (never breaks admin action)")


# ---------- endpoint instrumentation: ai_config ----------

def test_patch_ai_provider_audits_update():
    from app.api.admin import ai_providers as mod

    svc = MagicMock()
    svc.patch_setting.return_value = {"provider_key": "gigachat", "enabled": True}
    body = MagicMock()
    body.model_dump.return_value = {"temperature": 0.6, "enabled": True}
    db = MagicMock()
    with patch.object(mod, "AIProviderSettingsService", return_value=svc), \
         patch.object(mod, "log_admin_action") as log_mock:
        result = asyncio.run(mod.patch_ai_provider("gigachat", body, _fake_request(), None, db))
    assert result["provider_key"] == "gigachat"
    log_mock.assert_called_once()
    kwargs = log_mock.call_args.kwargs
    assert kwargs["action"] == "update"
    assert kwargs["resource_type"] == "ai_config"
    assert kwargs["resource_id"] == "gigachat"
    assert kwargs["changed_fields"] == ["enabled", "temperature"]
    print("PASS: PATCH ai-providers writes update audit with changed_fields")


# ---------- endpoint instrumentation: kb ----------

def test_approve_source_audits_kb():
    from app.api.admin import knowledge_base as mod

    svc = MagicMock()
    svc.approve_source.return_value = {"ok": True}
    sid = uuid.uuid4()
    db = MagicMock()
    with patch.object(mod, "AdmissionConsoleService", return_value=svc), \
         patch.object(mod, "log_admin_action") as log_mock:
        result = asyncio.run(mod.approve_source(sid, _fake_request(), None, db))
    assert result == {"ok": True}
    kwargs = log_mock.call_args.kwargs
    assert kwargs["action"] == "approve"
    assert kwargs["resource_type"] == "kb"
    assert kwargs["resource_id"] == sid
    print("PASS: approve-source writes kb audit")


# ---------- endpoint instrumentation: retrieval_tuning ----------

def test_cache_clear_audits_retrieval_tuning():
    from app.api.admin import retrieval as mod

    db = MagicMock()
    with patch("app.services.cache.retrieval_cache.clear", return_value=17), \
         patch.object(mod, "_cache_snapshot", return_value={"ok": True}), \
         patch.object(mod, "log_admin_action") as log_mock:
        result = mod.api_retrieval_cache_clear(_fake_request(), None, db)
    assert result["removed"] == 17
    kwargs = log_mock.call_args.kwargs
    assert kwargs["action"] == "cache_clear"
    assert kwargs["resource_type"] == "retrieval_tuning"
    assert kwargs["details"] == {"removed": 17}
    print("PASS: cache-clear writes retrieval_tuning audit with details")


def test_tuning_put_audits_retrieval_tuning():
    """PUT /admin/retrieval/tuning пишет аудит update. Регрессия 04.09.2026:
    в обработчике отсутствовали зависимости request/db (NameError → 500 на
    каждый вызов, тумблер кеша из консоли был недоступен)."""
    from app.api.admin import retrieval as mod

    body = MagicMock()
    body.model_dump.return_value = {"rag_top_k": 5}
    db = MagicMock()
    mgr = MagicMock()
    with patch.object(mod, "_patch_from_body", return_value={"rag_top_k": 5}), \
         patch.object(mod, "validate_patch", side_effect=lambda p: p), \
         patch.object(mod, "strip_keys_matching_env", side_effect=lambda m: m), \
         patch.object(mod, "get_retrieval_manager", return_value=mgr), \
         patch.object(mod, "store") as store_mock, \
         patch.object(mod, "log_admin_action") as log_mock:
        result = mod.api_retrieval_tuning_put(body, _fake_request(), None, db)
    store_mock.set_setting.assert_called_once()
    mgr.refresh.assert_called_once()
    assert "effective" in result and "field_sources" in result
    kwargs = log_mock.call_args.kwargs
    assert kwargs["action"] == "update"
    assert kwargs["resource_type"] == "retrieval_tuning"
    assert kwargs["changed_fields"] == ["rag_top_k"]
    print("PASS: tuning-put writes retrieval_tuning audit (request/db deps present)")


# ---------- endpoint instrumentation: system_prompt ----------

def test_activate_system_prompt_audits_system_prompt():
    from app.api.admin import prompt as mod

    svc = MagicMock()
    pid = uuid.uuid4()
    svc.activate.return_value = {"id": str(pid), "version": "v4"}
    db = MagicMock()
    with patch.object(mod, "SystemPromptService", return_value=svc), \
         patch.object(mod, "log_admin_action") as log_mock:
        result = asyncio.run(
            mod.activate_system_prompt(pid, _fake_request(), None, db)
        )
    assert result["id"] == str(pid)
    kwargs = log_mock.call_args.kwargs
    assert kwargs["action"] == "activate"
    assert kwargs["resource_type"] == "system_prompt"
    assert kwargs["resource_id"] == str(pid)
    print("PASS: prompt-activate writes system_prompt audit")


if __name__ == "__main__":
    import inspect
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ALL ADMIN ACTIONS AUDIT TESTS PASSED")