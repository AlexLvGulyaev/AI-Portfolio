"""
Memory contracts for AI Portfolio.

Source: Assistant Flow (services/memory/base.py)
Used directly without modifications.

Conversational memory — **separate subsystem** (not a helper inside orchestrator):
separate lifecycle through `ConversationMemoryService`, budget discipline, observability.
KB retrieval (RAG) **not** mixed with this read/write path.

Explicit separation:
- **dialog history** — persistent user/assistant replicas in PostgreSQL (this layer);
- **semantic memory** — future retrievable memory records (separate retrieval namespace), NOT implemented here;
- **KB retrieval context** — RAG chunks and intermediate context; not saved to dialog history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConversationMemoryRecord:
    """Single dialog history record (not semantic memory vector)."""

    message_id: str
    session_id: str
    user_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_id: str | None = None


@dataclass(frozen=True)
class ConversationMemoryQuery:
    """Query parameters (extensible without breaking API)."""

    session_id: str
    limit: int = 50


@dataclass(frozen=True)
class MemoryBudgetPolicy:
    """
    Constraints for recent messages (character approximation; token-aware — deferred).

    Conservative defaults: protection from context explosion before hybrid/memory retrieval.
    Read path: deterministic trim by `max_message_chars`, then hard cap by
    `total_memory_chars_budget` (no silent exceed of total output).
    """

    max_recent_messages: int = 50
    max_message_chars: int = 8000
    total_memory_chars_budget: int = 32000


@runtime_checkable
class ConversationMemoryServiceProtocol(Protocol):
    def get_recent_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        ...

    def get_session_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[ConversationMemoryRecord]:
        ...