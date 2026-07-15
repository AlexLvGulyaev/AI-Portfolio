"""
Public read-only API for project cards.

Source of Truth for project cards in the portfolio catalog is PostgreSQL.
This endpoint is consumed by the public vanilla frontend.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import ProjectCard

router = APIRouter()


def _icon_for_slug(slug: str) -> str:
    """Return SVG path for a project card based on slug.

    This is a presentation concern kept on the backend for the vanilla
    frontend. The icon is not part of the canonical ProjectCard data.
    """
    icons = {
        "assistant-flow": (
            "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        ),
        "review-flow": (
            "M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
        ),
        "lead-qualification": (
            "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
        ),
        "hr-assistant": (
            "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
        ),
        "prompt-review": (
            "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        ),
        "telegram-ai-gateway": (
            "M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
        ),
        "competitor-monitor": (
            "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
        ),
    }
    return icons.get(
        slug,
        "M13 10V3L4 14h7v7l9-11h-7z",  # default lightning-bolt icon
    )


@router.get("/project-cards")
async def list_project_cards(db: Session = Depends(get_db)):
    """Return visible project cards ordered by display_order."""
    cards = (
        db.query(ProjectCard)
        .filter(ProjectCard.is_visible.is_(True))
        .order_by(ProjectCard.display_order.asc())
        .all()
    )

    return {
        "items": [
            {
                "id": str(card.id),
                "slug": card.slug,
                "title": card.title,
                "short_description": card.short_description,
                "category": card.category,
                "tags": card.tags or [],
                "display_order": card.display_order,
                "show_on_homepage": card.show_on_homepage,
                "external_url": card.external_url,
                "icon_path": _icon_for_slug(card.slug),
            }
            for card in cards
        ],
    }
