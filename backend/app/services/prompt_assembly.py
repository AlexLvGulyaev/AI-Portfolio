"""
Prompt Assembly для AI Portfolio.

Единый механизм формирования полного prompt для LLM.

Состав промпта:
- System prompt
- Conversation memory
- RAG context
- User query
"""

from typing import Any

from app.services.memory.base import ConversationMemoryRecord


# System prompt для AI Portfolio
SYSTEM_PROMPT = """Ты — AI-ассистент портфолио AI-инженера.

Твоя задача — отвечать на вопросы о кейсах, услугах и технологиях.

Правила:
- Отвечай кратко и по существу
- Используй информацию из базы знаний
- Если информации нет в контексте, честно скажи об этом
- Не выдумывай информацию
- Отвечай на русском языке

Контекст из базы знаний:
{rag_context}

Предыдущий разговор:
{conversation_history}

Вопрос пользователя: {user_query}

Ответ:"""


class PromptAssembly:
    """
    Единый механизм формирования prompt.

    Prompt НЕ должен собираться внутри AI Provider.
    PromptAssembly — единственная точка сборки prompt.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_context_tokens: int = 3000,
    ):
        """
        Инициализация.

        Args:
            system_prompt: Системный промпт (если None, используется дефолтный)
            max_context_tokens: Максимальное количество токенов контекста
        """
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.max_context_tokens = max_context_tokens

    def build(
        self,
        user_query: str,
        *,
        conversation_memory: list[ConversationMemoryRecord] | None = None,
        rag_context: str | None = None,
    ) -> str:
        """
        Формирует полный prompt для LLM.

        Args:
            user_query: Запрос пользователя
            conversation_memory: История диалога
            rag_context: Контекст из RAG

        Returns:
            Полный prompt
        """
        # Форматируем историю диалога
        history = self._format_history(conversation_memory)

        # Форматируем RAG контекст
        context = rag_context or "Информация отсутствует."

        # Собираем prompt
        prompt = self.system_prompt.format(
            rag_context=context,
            conversation_history=history,
            user_query=user_query,
        )

        return prompt

    def _format_history(
        self, conversation_memory: list[ConversationMemoryRecord] | None
    ) -> str:
        """
        Форматирует историю диалога.

        Args:
            conversation_memory: История диалога

        Returns:
            Форматированная история
        """
        if not conversation_memory:
            return "История диалога отсутствует."

        lines: list[str] = []
        for msg in conversation_memory:
            role = "Пользователь" if msg.role == "user" else "Ассистент"
            lines.append(f"{role}: {msg.content}")

        return "\n".join(lines)

    def build_messages(
        self,
        user_query: str,
        *,
        conversation_memory: list[ConversationMemoryRecord] | None = None,
        rag_context: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Формирует messages в формате OpenAI.

        Альтернативный формат для провайдеров, поддерживающих messages API.

        Args:
            user_query: Запрос пользователя
            conversation_memory: История диалога
            rag_context: Контекст из RAG

        Returns:
            Список messages
        """
        messages: list[dict[str, str]] = []

        # System message с контекстом
        context = rag_context or "Информация отсутствует."
        system_content = f"""Ты — AI-ассистент портфолио AI-инженера.

Твоя задача — отвечать на вопросы о кейсах, услугах и технологиях.

Правила:
- Отвечай кратко и по существу
- Используй информацию из базы знаний
- Если информации нет в контексте, честно скажи об этом
- Не выдумывай информацию
- Отвечай на русском языке

Контекст из базы знаний:
{context}"""

        messages.append({"role": "system", "content": system_content})

        # История диалога
        if conversation_memory:
            for msg in conversation_memory:
                messages.append({"role": msg.role, "content": msg.content})

        # Текущий запрос
        messages.append({"role": "user", "content": user_query})

        return messages