"""
Admin system-prompt API for the AI settings console (task 2026-08-30).

Routes (all behind require_admin):

- GET    /system-prompt             — активная версия + история + builtin
- GET    /system-prompt/builtin     — вшитый шаблон (источник сброса)
- PUT    /system-prompt             — сохранить новую версию и активировать
- POST   /system-prompt/{id}/activate — вернуться на предыдущую версию
- POST   /system-prompt/reset       — активировать вшитый v4-compact-multi
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.admin.dependencies import require_admin
from app.core.database import get_db
from app.services.admin.system_prompt_service import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_VERSION,
    SystemPromptService,
)

router = APIRouter()


class SystemPromptUpdate(BaseModel):
    version: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1)
    note: str | None = Field(None, max_length=2000)


def _service(db: Session) -> SystemPromptService:
    return SystemPromptService(db)


@router.get("/system-prompt")
async def get_system_prompt(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Активная версия системного промпта + история версий + builtin."""
    return _service(db).get_state()


@router.get("/system-prompt/builtin")
async def get_builtin_prompt(
    admin: None = Depends(require_admin),
):
    """Вшитый системный промпт (v4-compact-multi) — источник сброса."""
    return {"version": SYSTEM_PROMPT_VERSION, "body": SYSTEM_PROMPT}


@router.put("/system-prompt")
async def save_system_prompt(
    payload: SystemPromptUpdate,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Сохранить тело промпта как новую версию и активировать."""
    try:
        row = _service(db).create_version(payload.version, payload.body, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_prompt", "message": str(exc)})
    return row


@router.post("/system-prompt/reset")
async def reset_system_prompt(
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Вернуть вшитый системный промпт (v4-compact-multi) как активный."""
    return _service(db).reset_to_builtin()


@router.post("/system-prompt/{prompt_id}/activate")
async def activate_system_prompt(
    prompt_id: uuid.UUID,
    admin: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Активировать существующую версию (откат к ней)."""
    try:
        return _service(db).activate(prompt_id)
    except LookupError:
        raise HTTPException(status_code=404, detail={"code": "system_prompt_not_found"})