"""Heading-aware KB chunking (owner decision 30.08.2026).

Документы-источники KB — SOT (файл задачи 2026-08-30,
heading-aware-chunking). Разбивает по заголовкам; секции атомарны,
окно фиксированной длины остаётся только для секций-переростков и
документов без заголовков (прежнее поведение).

Run inside the backend container: python tests/test_heading_aware_chunking.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.admin.github_knowledge_source_service import (  # noqa: E402
    GitHubKnowledgeSourceService,
)
from app.services.rag.knowledge_base_indexer import (  # noqa: E402
    KnowledgeBaseIndexer,
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")


def _indexer() -> KnowledgeBaseIndexer:
    """Чистые функции чанкера — store не нужен."""
    return KnowledgeBaseIndexer.__new__(KnowledgeBaseIndexer)


def _chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    return _indexer()._create_chunks(text, chunk_size=size, overlap=overlap)


def test_sections_are_atomic() -> None:
    print("[Heading sections atomic]")
    text = "\n\n".join(
        ["# Doc", "intro"] + [f"## S{i}\n" + "x" * 80 for i in range(8)]
    )
    chunks = _chunks(text, size=200, overlap=40)
    check("one chunk per section + intro", len(chunks) == 9, str(len(chunks)))
    heads = [c.splitlines()[0] for c in chunks]
    check(
        "headers intact",
        heads[0].startswith("# Doc") and heads[1:] == [f"## S{i}" for i in range(8)],
        str(heads),
    )
    merged = [c for c in chunks if "\n##" in c]
    check("no merged sections", not merged, repr(merged[:1]))


def test_oversized_section_uses_window() -> None:
    print("[Oversized section window]")
    big = "## Big\n" + "y" * 600
    chunks = _chunks(big, size=200, overlap=40)
    check("windowed into several", len(chunks) > 2, str(len(chunks)))
    check("first window keeps header", chunks[0].startswith("## Big"), chunks[0][:20])


def test_no_headings_keeps_fixed_window() -> None:
    print("[No headings -> fixed window]")
    flat = "z" * 1000
    chunks = _chunks(flat, size=500, overlap=50)
    check("3 windows", [len(c) for c in chunks] == [500, 500, 100],
          str([len(c) for c in chunks]))


def test_converter_keeps_headings_no_debris() -> None:
    print("[md->plain headings + no '>' debris]")
    md: str = (
        "## Как связаться?\n\n"
        "**Telegram: [@user](https://t.me/user)** — самый быстрый канал.\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n"
    )
    plain = GitHubKnowledgeSourceService._markdown_to_plain_text(md)
    check("h2 preserved", "## Как связаться?" in plain, repr(plain[:40]))
    debris = [line for line in plain.splitlines() if ">" in line]
    check("no stray '>'", not debris, repr(debris[:1]))
    check("link text kept", "@user" in plain, repr(plain[:80]))


def test_glossary_n8n_chunk_atomic() -> None:
    """Контроль кейса из диагностики: секция «## n8n» — собственный чанк."""
    print("[GLOSSARY n8n atomic]")
    glossary = Path(__file__).resolve().parents[2] / "docs" / "GLOSSARY.md"
    if not glossary.exists():
        check("glossary source present", False, str(glossary))
        return
    plain = GitHubKnowledgeSourceService._markdown_to_plain_text(
        glossary.read_text(encoding="utf-8")
    )
    chunks = _chunks(plain)
    n8n = [c for c in chunks if c.startswith("## n8n")]
    check("single n8n chunk", len(n8n) == 1, str(len(n8n)))
    check("definition inside", "low-code" in (n8n[0] if n8n else ""), "")


if __name__ == "__main__":
    test_sections_are_atomic()
    test_oversized_section_uses_window()
    test_no_headings_keeps_fixed_window()
    test_converter_keeps_headings_no_debris()
    test_glossary_n8n_chunk_atomic()
    print(f"\nPASSED {len(PASS)} / FAILED {len(FAIL)}")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        sys.exit(1)