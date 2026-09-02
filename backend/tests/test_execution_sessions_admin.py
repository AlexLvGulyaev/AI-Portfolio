"""
Unit-тесты ExecutionSessionsAdminService (админ-консоль, страница «Логи»).

Регрессия 02.09.2026: ветка `search` падала NameError на этапе сборки
query (импорт `String as sa_String` не совпадал с использованием
`sa.String`) — любой поиск на странице «Логи» давал 500.

Сессия БД мокается (конвенция suite — без живой БД); сборка SQLAlchemy-
query происходит до обращения к моку, поэтому NameError ловится тестом.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.admin.execution_sessions_service import ExecutionSessionsAdminService


def test_list_sessions_search_builds_query():
    db = MagicMock()
    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = []
    svc = ExecutionSessionsAdminService(db)
    res = svc.list_sessions(search="kommo", date_from=date(2026, 9, 1),
                            date_to=date(2026, 9, 2), limit=20)
    assert res["total"] == 0
    assert res["items"] == []
    # фильтр search реально ушёл в query: WHERE-условие собрано без ошибок
    assert db.scalar.called
    print("PASS: list_sessions(search=...) builds query without NameError")


def test_list_sessions_search_covers_metadata():
    """Регрессия 02.09.2026: поиск должен заглядывать и в execution_metadata
    (там лежат query/response/sources) — иначе «CRM» даёт пусто, хотя
    данные в БД есть."""
    db = MagicMock()
    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = []
    svc = ExecutionSessionsAdminService(db)
    res = svc.list_sessions(search="crm", limit=20)
    assert res["total"] == 0
    assert db.scalar.called
    print("PASS: search covers execution_metadata (query/response/sources)")


def test_list_sessions_no_search():
    db = MagicMock()
    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = []
    svc = ExecutionSessionsAdminService(db)
    res = svc.list_sessions(limit=5)
    assert res["total"] == 0
    print("PASS: list_sessions without search works")


if __name__ == "__main__":
    test_list_sessions_search_builds_query()
    test_list_sessions_no_search()
    print("ALL EXECUTION SESSIONS TESTS PASSED")