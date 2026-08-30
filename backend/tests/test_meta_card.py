"""
Мета-карточка платформы AI Portfolio ("Это Я", решение владельца 30.08.2026).

Покрывает:
- исключение мета-карточки из чат-реестра PortfolioRegistry в ОБЕИХ
  режимах (публичный и admin include_hidden);
- гвард delete: DELETE мета-карточки → 409 meta_card_protected;
- гвард PATCH: изменение параметров дисплея на мета-карточке → жёсткий 400
  (meta_card_display_locked), текстовые поля редактируются свободно;
- публичный каталог: is_meta-карточка is_visible=false не попадает в
  /project-cards (лендинг).
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.entities import ProjectCard
from app.services.admin.knowledge_base_service import KnowledgeBaseService
from app.services.portfolio_registry import PortfolioRegistry

# ---------- Fake DB для реестра (учитывает is_meta в SQL) ----------

Row = SimpleNamespace


class MetaAwareFakeDB:
    """Строки из БД отдаются только с реальным SQL-фильтром is_meta (B1 и реестр)."""

    def __init__(self, cards, sources=None):
        self._cards = cards
        self._sources = sources or []

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    def execute(self, query, *a, **kw):
        q = str(query)
        if "JOIN project_cards" in q:
            # B1-гвард скрытых репозиториев: источники, привязанные к
            # невидимым НЕ-мета карточкам. Если SQL не отфильтровал is_meta,
            # фейк вернёт и мета-источник, и тест упадёт.
            if "is_meta = false" in q:
                hidden = [r.identifier for r in self._sources
                          if not r.card_is_visible and not r.card_is_meta]
                return self._Result([Row(identifier=i) for i in hidden])
            return self._Result([Row(identifier=r.identifier) for r in self._sources])
        if "FROM project_cards" in q:
            if "is_meta = false" not in q:
                # Запрос без фильтра is_meta вернул бы мета-карточку — дефект.
                return self._Result(list(self._cards))
            if "is_visible = true" in q:
                return self._Result([c for c in self._cards
                                     if c.is_visible and not c.is_meta])
            return self._Result([c for c in self._cards
                                 if not c.is_visible and not c.is_meta])
        if "knowledge_sources" in q:
            return self._Result([Row(identifier=r.identifier) for r in self._sources])
        raise AssertionError("unexpected query: " + q[:120])


def make_registry(cards, include_hidden=False, sources=()):
    return PortfolioRegistry(MetaAwareFakeDB(cards, sources), include_hidden=include_hidden)


def _source(identifier, card_is_visible, card_is_meta=False):
    return Row(identifier=identifier, card_is_visible=card_is_visible,
               card_is_meta=card_is_meta)


def test_b1_guard_keeps_meta_card_sources_retrievable():
    """Вычет-гвард: репозиторий невидимой мета-карточки НЕ попадает в скрываемые.

    B1 (решение 29.08) прячет документы невидимых карточек от публичного чата.
    Мета-карточка ("Это Я") — исключение: метапак — публичные знания зрителя.
    """
    sources = [
        _source("AlexLvGulyaev/ai-portfolio", card_is_visible=False, card_is_meta=True),
        _source("AlexLvGulyaev/DraftSecretRepo", card_is_visible=False),
    ]
    rows = [_card("ai-portfolio", is_meta=True, is_visible=False), _card("hr-assistant")]
    r = make_registry(rows, sources=sources)
    assert "AlexLvGulyaev/ai-portfolio" not in r.hidden_repos
    assert "AlexLvGulyaev/DraftSecretRepo" in r.hidden_repos
    # Гвард выдачи не режет мета-репозиторий.
    guard = r.public_guard()
    assert guard is None or "AlexLvGulyaev/ai-portfolio" not in str(guard)
    print("PASS: B1 guard keeps meta card sources retrievable in public chat")


def test_hidden_cards_negation_excludes_meta_card():
    """Явное отрицание по скрытым карточкам не должно считать мета-карточку скрытым проектом."""
    source = _source("AlexLvGulyaev/ai-portfolio", card_is_visible=False, card_is_meta=True)
    r = make_registry(
        [_card("ai-portfolio", is_meta=True, is_visible=False)],
        sources=[source],
    )
    meta_repo = "AlexLvGulyaev/ai-portfolio"
    assert meta_repo in r.repos  # источник допущен в KB
    assert meta_repo not in r.hidden_repos
    print("PASS: hidden-card negation logic excludes meta card")


def _card(slug, is_meta=False, is_visible=True):
    return Row(
        slug=slug, title=slug.upper(), short_description="d", category="cases",
        tags=[], display_order=1, external_url=None, is_meta=is_meta,
        is_visible=is_visible,
    )


def test_registry_excludes_meta_card_in_public_mode():
    """Мета-карточка не попадает в публичный чат-реестр, даже если is_visible=true."""
    rows = [_card("ai-portfolio", is_meta=True, is_visible=True), _card("hr-assistant")]
    r = make_registry(rows, include_hidden=False)
    assert [c.slug for c in r.cards] == ["hr-assistant"]
    print("PASS: registry excludes meta card (public mode)")


def test_registry_excludes_meta_card_in_include_hidden_mode():
    """Admin-режим include_hidden тоже не видит мета-карточку (§ «Это Я»)."""
    rows = [_card("ai-portfolio", is_meta=True, is_visible=True),
            _card("draft-project", is_visible=False)]
    r = make_registry(rows, include_hidden=True)
    slugs = [c.slug for c in r.cards]
    assert "ai-portfolio" not in slugs
    assert "draft-project" in slugs
    print("PASS: registry excludes meta card (include_hidden mode)")


# ---------- Сервисные гварды ----------

CARD_ID = uuid.uuid4()


def _meta_row():
    return SimpleNamespace(
        id=CARD_ID, slug="ai-portfolio", title="AI Portfolio",
        short_description="Сама платформа", category="meta", tags=["Meta"],
        display_order=0, show_on_homepage=0, is_visible=False,
        is_child_project=False, is_meta=True,
        knowledge_content=None, external_url="https://ai.alex-n8n.site",
        created_at=None, updated_at=None,
    )


def _service_with(row):
    db = MagicMock()
    db.get.return_value = row
    return KnowledgeBaseService(db), db


def test_delete_meta_card_returns_409_meta_card_protected():
    svc, _ = _service_with(_meta_row())
    try:
        svc.delete_project_card(CARD_ID)
        raised = None
    except HTTPException as exc:
        raised = exc
    assert raised is not None, "DELETE мета-карточки должен отклоняться"
    assert raised.status_code == 409
    assert raised.detail["code"] == "meta_card_protected"
    print("PASS: DELETE meta card -> 409 meta_card_protected")


def test_patch_meta_card_display_params_hard_400():
    svc, _ = _service_with(_meta_row())
    with pytest.raises(HTTPException) as exc_info:
        svc.update_project_card(CARD_ID, {"is_visible": True, "slug": "new-slug"})
    exc = exc_info.value
    assert exc.status_code == 400
    assert exc.detail["code"] == "meta_card_display_locked"
    # Жёсткий 400: оба изменённых поля перечислены, независимо от порядка.
    assert sorted(exc.detail["fields"]) == ["is_visible", "slug"]
    assert exc.detail["fields"] == sorted(exc.detail["fields"])
    print("PASS: PATCH display params on meta card -> hard 400 meta_card_display_locked")


def test_patch_meta_card_text_fields_allowed():
    row = _meta_row()
    svc, db = _service_with(row)
    result = svc.update_project_card(CARD_ID, {"title": "AI Portfolio — платформа"})
    assert result["title"] == "AI Portfolio — платформа"
    db.commit.assert_called_once()
    print("PASS: PATCH text fields on meta card allowed")


def test_patch_regular_card_display_params_still_allowed():
    row = SimpleNamespace(**{**vars(_meta_row()), "is_meta": False})
    svc, _ = _service_with(row)
    result = svc.update_project_card(CARD_ID, {"is_visible": False})
    assert result["is_visible"] is False
    print("PASS: PATCH display params on regular card unaffected")


def test_create_card_persists_is_meta_flag():
    db = MagicMock()
    # db.scalars(...).first() -> None: slug свободен
    db.scalars.return_value.first.return_value = None
    svc = KnowledgeBaseService(db)
    svc.create_project_card({
        "slug": "ai-portfolio", "title": "AI Portfolio",
        "short_description": "Мета-карточка платформы", "is_meta": True,
    })
    added = db.add.call_args[0][0]
    assert added.is_meta is True
    print("PASS: create persists is_meta flag")

# ---------- index_store_for: chroma-активный путь записи KB ----------

def test_index_store_for_wraps_legacy_ragservice():
    """Активный chroma-бэкенд (RAGService, только поиск) оборачивается в ChromaIndexStore.

    До фикса sync падал ValueError: backend 'RAGService' does not support
    KB indexing — фолбэк в sync был недостижим."""
    from unittest.mock import MagicMock as _MagicMock
    from app.services.rag.knowledge_base_indexer import ChromaIndexStore, index_store_for

    from app.services.rag.rag_service import RAGService
    fake_rag = _MagicMock(spec=RAGService)  # spec=True: isinstance проходит
    store = index_store_for(fake_rag)
    assert store.backend_name == "chroma"
    print("PASS: legacy RAGService wrapped into ChromaIndexStore")


def test_index_store_for_still_rejects_unsupported_backend():
    from app.services.rag.knowledge_base_indexer import index_store_for

    foreign = SimpleNamespace()  # нет add_chunks и не RAGService
    try:
        index_store_for(foreign)
        raised = None
    except ValueError as exc:
        raised = exc
    assert raised is not None
    assert "does not support" in str(raised)
    print("PASS: unsupported backend still rejected")
