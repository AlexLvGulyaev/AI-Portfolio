"""
Response DTO для AI Portfolio.

Единый внутренний объект ответа, содержащий все метаданные.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class ChatResponseDTO:
    """
    Единый внутренний объект ответа.

    Содержит:
    - answer: текст ответа
    - provider: использованный провайдер
    - model: использованная модель
    - cache_hit: был ли ответ из кеша
    - rag_used: использовался ли RAG
    - sources: источники из базы знаний
    - latency_ms: время ответа в миллисекундах
    - session_id: ID сессии
    - user_id: ID посетителя
    - metadata: дополнительные метаданные
    """

    answer: str
    session_id: UUID
    user_id: UUID | None = None
    provider: str = ""
    model: str = ""
    cache_hit: bool = False
    rag_used: bool = False
    sources: list[str] = field(default_factory=list)
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Преобразует DTO в словарь для API ответа."""
        return {
            "answer": self.answer,
            "session_id": str(self.session_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "provider": self.provider,
            "model": self.model,
            "from_cache": self.cache_hit,
            "rag_used": self.rag_used,
            "sources": self.sources,
            "latency_ms": self.latency_ms,
        }

    def to_api_response(self) -> dict[str, Any]:
        """
        Преобразует DTO в формат API ответа.

    Соответствует схеме ChatResponse из schemas/chat.py.
    """
        return {
            "answer": self.answer,
            "session_id": str(self.session_id),
            "sources": self.sources,
            "provider": self.provider,
            "from_cache": self.cache_hit,
            "response_time_ms": self.latency_ms,
        }