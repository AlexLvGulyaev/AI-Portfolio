"""Morphic-проба: подбор релевантных кейсов под задачу зрителя (экран 1b).

POST /case-match {task} → до 3 кейсов {slug, title, why}.
Grounded: retrieval по документам KB + реестр видимых карточек проекта;
объяснение применимости генерирует LLM по документам (без обещаний
статусов и цен). Scope пробы (решение владельца 03.09.2026): без кеша,
без сессий, без визарда; откат — флаг на фронте + revert коммита.
"""

import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.portfolio_registry import PortfolioRegistry
from app.services.rag.retrieval_manager import get_retrieval_manager
from app.services.ai_provider_settings_service import AIProviderSettingsService
from app.services.providers.factory import AIProviderFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/case-match", tags=["case-match"])

MAX_TASK_CHARS = 500
MAX_ITEMS = 3
MAX_SNIPPETS = 8
SNIPPET_CHARS = 320

_SYSTEM_RULES = """\
Ты — подборщик решений AI-портфолио. Зритель описал свою задачу.
Выбери до 3 проектов реестра, наиболее релевантных задаче.

Правила:
- «why» — одна строка до 140 символов: почему этот проект решает задачу.
- Опирайся только на описания карточек и приведённые фрагменты
  документации. Не обещай статусов («реализовано»), сроков и цен.
- Фрагменты документации подписаны «репозиторий · путь». Факт можно
  приписать проекту, только если фрагмент подписан его репозиторием.
- В «why» — только факты, подтверждённые карточкой или фрагментами
  документации этого проекта. Формулировки задачи зрителя не переноси в
  описание проекта: если из карточки и его фрагментов не следует, что
  проект умеет X, не утверждай «с X».
- Если прямого соответствия нет — выбери 1-2 ближайших по смыслу и
  честно скажи об этом в «why» («прямого кейса про X нет, ближайший…»).
- Отвечай СТРОГО JSON-массивом без пояснений: [{"slug": "...", "why": "..."}]\
"""


class CaseMatchRequest(BaseModel):
    task: str = Field(..., min_length=5, max_length=MAX_TASK_CHARS)


class CaseMatchItem(BaseModel):
    slug: str
    title: str
    why: str


class CaseMatchResponse(BaseModel):
    items: list[CaseMatchItem]
    provider: Optional[str] = None
    model: Optional[str] = None


def _render_cards(cards: list) -> str:
    return "\n".join(
        f"- {c.slug} | {c.title} | {c.short_description}"
        for c in cards
    )


def _render_snippets(results) -> str:
    """Фрагменты подписаны репозиторием: LLM не приписывает чужие факты проекту.

    Root cause (03.09.2026): без подписи репозитория фрагмент чужого кейса
    (Lead-Qualification-MVP «попадают в CRM без участия менеджера») модель
    приписала карточке TIB. Подпись `<репозиторий> · <путь>` даёт модели
    привязку фрагмента к проекту (см. PROMPT_ARCHITECTURE §7).
    """
    parts = []
    for r in results[:MAX_SNIPPETS]:
        text = re.sub(r"\s+", " ", (r.content or "")).strip()
        if not text:
            continue
        repo = ((getattr(r, "metadata", None) or {}).get("repo") or "")
        short = repo.rsplit("/", 1)[-1] if repo else ""
        src = f"{short} · {r.source}" if short else r.source
        parts.append(f"[{src}] {text[:SNIPPET_CHARS]}")
    return "\n\n".join(parts) if parts else "(фрагменты не найдены)"


def _extract_json(raw: str) -> Any:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON array in LLM output")
    return json.loads(text[start : end + 1])


@router.post("", response_model=CaseMatchResponse)
async def case_match(
    payload: CaseMatchRequest,
    db: Session = Depends(get_db),
) -> CaseMatchResponse:
    """Подбор до 3 кейсов под задачу зрителя с объяснением применимости."""
    # Нормализуем ввод: схлопываем пробелы, режем длину
    task = re.sub(r"\s+", " ", payload.task).strip()[:MAX_TASK_CHARS]
    if len(task) < 5:
        raise HTTPException(status_code=422, detail="task_too_short")

    registry = PortfolioRegistry(db)  # load() внутри __init__
    cards = registry.cards
    if not cards:
        raise HTTPException(status_code=503, detail="registry_empty")

    # 1. Retrieval по документам KB (глобальный поиск)
    try:
        rag = get_retrieval_manager().get_backend()
        results = rag.search(task, top_k=MAX_SNIPPETS)
    except Exception as e:  # retrieval недоступен — подбор всё равно возможен
        logger.warning("case-match retrieval unavailable: %s", e)
        results = []

    # 2. Компактный промпт: реестр + фрагменты + задача
    prompt = (
        f"{_SYSTEM_RULES}\n\n"
        f"Реестр проектов:\n{_render_cards(cards)}\n\n"
        f"Фрагменты документации:\n{_render_snippets(results)}\n\n"
        f"Задача зрителя: {task}\n\n"
        f"JSON:"
    )

    # 3. LLM с failover (как в chat_orchestrator, но компактно)
    provider_settings = AIProviderSettingsService(db)
    active, fallback = provider_settings.get_active_with_fallback()
    answer, provider_key, model_name = None, None, None
    for cfg_row in (active, fallback):
        if not cfg_row:
            continue
        try:
            cfg = provider_settings.build_effective_config(cfg_row)
            provider = AIProviderFactory.create(cfg.provider_key, config=cfg)
            answer = await provider.generate(
                prompt, temperature=0.2, max_tokens=500
            )
            provider_key, model_name = cfg.provider_key, cfg.model_name
            break
        except Exception as e:
            logger.warning("case-match provider %s failed: %s",
                           getattr(cfg_row, "provider_key", "?"), e)
    if not answer:
        raise HTTPException(status_code=503, detail="provider_unavailable")

    # 4. Парсинг и валидация против реестра
    try:
        parsed = _extract_json(answer)
    except ValueError:
        logger.warning("case-match unparseable LLM output")
        raise HTTPException(status_code=503, detail="match_parse_failed")

    by_slug = {c.slug: c for c in cards}
    items: list[CaseMatchItem] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug", "")).strip()
        why = str(entry.get("why", "")).strip()
        card = by_slug.get(slug)
        if not card or not why:
            continue
        items.append(
            CaseMatchItem(slug=slug, title=card.title, why=why[:200])
        )
        if len(items) >= MAX_ITEMS:
            break

    if not items:
        raise HTTPException(status_code=503, detail="match_empty")

    return CaseMatchResponse(items=items, provider=provider_key, model=model_name)