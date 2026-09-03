"""Панель документа: локализация чанка в plain-тексте (03.09.2026).

Чанки KB — подстроки `_markdown_to_plain_text` (markdown → HTML → текст),
не raw md. Фикс после репорта владельца: чанк PORTFOLIO_OVERVIEW с
буллетами/жирностью не находился в raw md.
"""

from app.api.document_fragment import _build_window, _insert_markers, _locate
from app.services.admin.github_knowledge_source_service import (
    GitHubKnowledgeSourceService,
)

MD = """# 🗺️ Карта портфеля AI Portfolio

Карта реализованных проектов: для каждого направления — что уже решено.

Коротко о направлениях:

- **RAG-ассистенты и базы знаний** — доступ к документации через поиск;
- **Голосовая первая линия** — транскрибация, голосовые ассистенты;

Ещё абзац после списка.
"""


def _plain() -> str:
    return GitHubKnowledgeSourceService._markdown_to_plain_text(MD)


def test_plain_text_drops_bullets_and_bold():
    plain = _plain()
    assert "**RAG-ассистенты" not in plain
    assert "- **" not in plain
    assert "RAG-ассистенты и базы знаний" in plain
    # Заголовки переживают трансформ — на них чанкуется и выравнивается окно.
    assert plain.startswith("# 🗺️ Карта портфеля AI Portfolio")


def test_chunk_from_plain_locates_in_plain_not_in_raw():
    plain = _plain()
    chunk = plain[plain.index("RAG-ассистенты"): plain.index("Ещё абзац")].strip()
    assert chunk  # чанк построен секционным чанкованием по plain
    # В raw md этого чанка нет (есть буллеты/жирность)…
    raw_span = _locate(MD, chunk)
    # …а в plain он локализуется точно.
    span = _locate(plain, chunk)
    assert span is not None
    assert raw_span is None or chunk not in MD


def test_window_and_markers_roundtrip():
    plain = _plain()
    chunk = "RAG-ассистенты и базы знаний"
    span = _locate(plain, chunk)
    assert span is not None
    start, end = _build_window(plain, span[0], span[1], 200)
    frag = plain[start:end].strip()
    h = _locate(frag, chunk)
    assert h is not None
    marked = _insert_markers(frag, h[0], h[1])
    assert marked.count("\ue000") == 1 and marked.count("\ue001") == 1
    before, highlighted, after = (
        marked.split("\ue000")[0],
        marked.split("\ue000")[1].split("\ue001")[0],
        marked.split("\ue001")[1],
    )
    assert chunk in before + highlighted + after
    assert marked.index(chunk) >= marked.index("\ue000")