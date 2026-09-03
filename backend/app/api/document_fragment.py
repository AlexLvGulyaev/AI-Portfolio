"""Панель документа: фрагмент md-документа вокруг цитированного чанка.

GET /document-fragment?repo=...&path=...&excerpt=...
→ крупный статический фрагмент документа с подсвеченным цитированным
чанком (решение владельца 03.09.2026: не полный md со скроллом, а
достаточно большой фрагмент с контекстом).

Механика: полный md берётся с raw.githubusercontent.com (ветка — из
реестра допуска KnowledgeSource, fail-closed: нет записи — 404); чанк
— точная подстрока документа (секционное чанкование), ищется после
схлопывания пробелов с обратной картой в исходные оффсеты. Подсветка —
PUA-маркеры / вокруг чанка, фронт разворачивает их в <mark>
после markdown-рендера.
"""

import logging
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import KnowledgeSource, ProjectCard
from app.services.rag.source_labels import github_blob_url, make_source_label

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-fragment", tags=["document-fragment"])

RAW_TIMEOUT_S = 8
MAX_DOC_CHARS = 1_000_000
MAX_EXCERPT_CHARS = 2000
DEFAULT_CONTEXT_CHARS = 3500
MAX_CONTEXT_CHARS = 8000
CACHE_TTL_S = 600
MAX_CACHE_DOCS = 128

# Символы Private Use Area: проходят через markdown-рендер как текст,
# фронт разворачивает их в <mark>. Не встречаются в осмысленных md.
MARK_OPEN = "\ue000"  # U+E000 PUA
MARK_CLOSE = "\ue001"  # U+E001 PUA

# (repo, branch, path) -> (fetched_at, text)
_raw_cache: dict[tuple[str, str, str], tuple[float, str]] = {}


def _fetch_raw(repo: str, branch: str, path: str) -> str:
    key = (repo, branch, path)
    hit = _raw_cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    resp = httpx.get(url, timeout=RAW_TIMEOUT_S, follow_redirects=True)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=404, detail=f"document_not_found:{resp.status_code}"
        )
    text = resp.text[:MAX_DOC_CHARS]
    _raw_cache[key] = (time.time(), text)
    if len(_raw_cache) > MAX_CACHE_DOCS:  # гигиена кеша
        oldest = min(_raw_cache, key=lambda k: _raw_cache[k][0])
        _raw_cache.pop(oldest, None)
    return text


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Схлопывание пробелов + обратная карта: norm[i] = оффсет в text."""
    norm: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            if norm and norm[-1] != " ":
                norm.append(" ")
                offsets.append(i)
        else:
            norm.append(ch)
            offsets.append(i)
    return "".join(norm), offsets


def _locate(doc: str, excerpt: str) -> tuple[int, int] | None:
    """Оффсеты чанка в документе после схлопывания пробелов."""
    norm_doc, doc_map = _normalize_with_map(doc)
    norm_exc, _ = _normalize_with_map(excerpt.strip())
    idx = norm_doc.find(norm_exc)
    if idx == -1:
        return None
    start = doc_map[idx]
    end = doc_map[idx + len(norm_exc) - 1] + 1
    return start, end


def _heading_starts(text: str) -> list[int]:
    return [m.start() for m in re.finditer(r"^#{1,6} ", text, flags=re.M)]


def _build_window(doc: str, exc_start: int, exc_end: int, context_chars: int) -> tuple[int, int]:
    """Окно ±context_chars/2 вокруг чанка; края тянутся к заголовкам."""
    half = context_chars // 2
    start = max(0, exc_start - half)
    end = min(len(doc), exc_end + half)
    # Левый край: ближайший заголовок внутри левой надстройки — фрагмент
    # начинается с секции, а не с середины строки.
    for h in _heading_starts(doc):
        if start < h < exc_start:
            start = h
            break
    # Правый край: следующий заголовок внутри правой надстройки.
    next_h = [h for h in _heading_starts(doc) if exc_end < h < end]
    if next_h:
        end = max(end, next_h[0])
    return start, end


def _insert_markers(text: str, h_start: int, h_end: int) -> str:
    return (
        text[:h_start] + MARK_OPEN + text[h_start:h_end] + MARK_CLOSE +
        text[h_end:]
    )


@router.get("")
async def document_fragment(
    repo: str = Query(..., min_length=3, max_length=200),
    path: str = Query(..., min_length=1, max_length=400),
    excerpt: str = Query(..., min_length=5, max_length=MAX_EXCERPT_CHARS),
    context_chars: int = Query(DEFAULT_CONTEXT_CHARS, ge=500, le=MAX_CONTEXT_CHARS),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Фрагмент документа вокруг цитированного чанка с подсветкой."""
    repo = repo.strip()
    path = path.strip().lstrip("/")
    excerpt = excerpt[:MAX_EXCERPT_CHARS]

    # Реестр допуска: только известные GitHub-источники, ветка — из БД;
    # читабельное имя — display_name, фолбэк — title карточки (как в цитатах)
    row = (
        db.query(
            KnowledgeSource.branch,
            KnowledgeSource.display_name,
            ProjectCard.title,
        )
        .outerjoin(ProjectCard, KnowledgeSource.project_card_id == ProjectCard.id)
        .filter(
            KnowledgeSource.identifier == repo,
            KnowledgeSource.source_type == "github_repo",
        )
        .first()
    )
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="repo_not_allowed")
    branch, display_name, card_title = row

    doc = _fetch_raw(repo, branch, path)
    label = make_source_label(display_name or card_title or repo, path)
    html_url = github_blob_url(repo, branch, path)

    located_span = _locate(doc, excerpt)
    if located_span is None:
        # Чанк не найден в текущем виде файла (документ правили после
        # индексации): честный фолбэк — показываем сам чанк целиком.
        located = False
        fragment = _insert_markers(excerpt.strip(), 0, len(excerpt.strip()))
    else:
        located = True
        exc_start, exc_end = located_span
        win_start, win_end = _build_window(
            doc, exc_start, exc_end, context_chars
        )
        fragment = doc[win_start:win_end].strip()
        h = _locate(fragment, excerpt)
        if h is None:  # не должно случиться, но не роняем панель
            fragment = _insert_markers(excerpt.strip(), 0, len(excerpt.strip()))
        else:
            fragment = _insert_markers(fragment, h[0], h[1])

    return {
        "label": label,
        "html_url": html_url,
        "repo": repo,
        "path": path,
        "branch": branch,
        "fragment": fragment,
        "located": located,
        "total_chars": len(doc),
    }