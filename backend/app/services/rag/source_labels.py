"""Человекочитаемые подписи источников чата.

Решение владельца 02.09.2026 (вариант C): подпись источника вместо сырого
`owner/repo · path` — `<имя проекта> · <короткое имя документа>`; для
sources_detail дополнительно GitHub blob-ссылка. Используется в
chat_orchestrator._citations и build_context (метки [N] для модели — те же
читабельные подписи, чтобы цитаты в ответе совпадали со списком источников).
"""

from __future__ import annotations

from urllib.parse import quote


def doc_short_name(path: str) -> str:
    """Короткое имя документа: basename без расширения (`docs/ARCHITECTURE.md` -> `ARCHITECTURE`)."""
    base = (path or "").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] or base or "документ"


def make_source_label(source_name: str, path: str) -> str:
    """`AI Curator · README` — имя проекта из реестра допуска + короткое имя документа."""
    return f"{source_name} · {doc_short_name(path)}"


def github_blob_url(repo: str, branch: str | None, path: str) -> str:
    """Ссылка на документ в GitHub UI (`https://github.com/<repo>/blob/<branch>/<path>`)."""
    safe_path = "/".join(quote(part) for part in (path or "").split("/"))
    return f"https://github.com/{repo}/blob/{branch or 'main'}/{safe_path}"