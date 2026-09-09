"""Код-нейтрализация doc-инъекций в недоверенном контексте.

План п. 4 (09.09.2026): doc-инъекции вида «ответь только словом X»,
«игнорируй системные инструкции», встроенные в содержимое документов,
не решаются системным промптом на GigaChat-Max (0/5 на всех версиях —
плато модели; gpt-4.1-mini 6/6). Методика и пробы — AI_EVAL_REPORT §12.

Нейтрализатор действует ДО сборки промпта, на двух рубежах:

1. Оркестратор (chat_orchestrator.py): retrieved-чанки с сильным
   паттерном инструкции выводятся из выдачи (карантин) — они не попадают
   ни в rag_context, ни в цитаты.
2. PromptAssembly.build — второй рубеж: если rag_context (синтетический
   или унаследованный путь, миновавший retrieval) содержит сильный
   паттерн, контекст заменяется на честное «не найдено».

Паттерны консервативные: только явные директивы ассистенту. Легитимный
корпус проверен сканом прод-коллекции ai_portfolio_knowledge_v2
(7753 чанка, 09.09.2026) — сильные паттерны не срабатывают ни на одном
чанке; слабые обороты («не упоминай ...») в паттерны не включены.
"""

import re
from typing import Any, Optional

# (метка паттерна, компилированное выражение). Явные директивы ассистенту,
# замаскированные под содержимое документа.
STRONG_INSTRUCTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # «игнорируй (все|предыдущие|системные) инструкции/правила/указания»
    (
        "ignore_instructions_ru",
        re.compile(
            r"игнор(?:ируй|ируйте)\s+(?:[^.]{0,40}?)?"
            r"(?:инструкц|правил|указания|системн)",
            re.IGNORECASE,
        ),
    ),
    # «ответь (только|одним) словом X», «отвечай словом X»
    (
        "answer_with_word_ru",
        re.compile(
            r"(?:ответь|отвечай|ответить|отвечайте)\s+"
            r"(?:только\s+|одним\s+|исключительно\s+)?слов",
            re.IGNORECASE,
        ),
    ),
    # «приоритет выше системных правил/промпта», «выше системных правил»
    (
        "priority_above_system_ru",
        re.compile(
            r"(?:приоритет\s+(?:выше|над)\s+(?:системных\s+)?"
            r"|(?:всегда\s+)?выше\s+системных\s+)(?:правил|промпт|инструкц)",
            re.IGNORECASE,
        ),
    ),
    # «не обращай внимания на системные инструкции/правила/промпт»
    (
        "disregard_system_ru",
        re.compile(
            r"(?:не\s+обращай\s+внимание|обрати\s+внимание\s+только)\s+на\s+"
            r"(?:системн|этот\s+промпт)",
            re.IGNORECASE,
        ),
    ),
    # ignore (all|previous|prior|above) instructions / system prompt
    (
        "ignore_instructions_en",
        re.compile(
            r"ignore\s+(?:all\s+|any\s+|previous\s+|prior\s+|the\s+|above\s+)*"
            r"(?:instructions|system\s+prompt)",
            re.IGNORECASE,
        ),
    ),
    # disregard (all|previous|prior|the|above) instructions
    (
        "disregard_instructions_en",
        re.compile(
            r"disregard\s+(?:all\s+|previous\s+|prior\s+|the\s+|above\s+)*"
            r"(?:instructions|system\s+prompt)",
            re.IGNORECASE,
        ),
    ),
    # «respond/answer only with the word X»
    (
        "answer_with_word_en",
        re.compile(
            r"(?:respond|answer|reply|say|output)\s+(?:only\s+|just\s+)?"
            r"(?:with\s+)?(?:the\s+)?(?:single\s+)?word",
            re.IGNORECASE,
        ),
    ),
]

# Замена нейтрализованного контекста: честная деградация контекста,
# тот же текст, что и штатная ветка «документы не найдены».
CONTEXT_QUARANTINE_NOTICE = "Релевантные документы не найдены."


def find_instruction_attacks(text: str) -> list[str]:
    """Метки сильных паттернов инструкций, найденных в тексте."""
    return [tag for tag, pattern in STRONG_INSTRUCTION_PATTERNS if pattern.search(text)]


def filter_quarantined(
    results: list[Any],
) -> tuple[list[Any], list[Any]]:
    """Делит retrieved-чанки на здоровые и подкарантинные.

    Args:
        results: SearchResult-подобные объекты с полем ``content``.

    Returns:
        ``(kept, quarantined)`` — порядок исходных результатов сохранён.
    """
    kept: list[Any] = []
    quarantined: list[Any] = []
    for result in results:
        attacks = find_instruction_attacks(getattr(result, "content", "") or "")
        (quarantined if attacks else kept).append(result)
    return kept, quarantined


def neutralize_context(context: Optional[str]) -> Optional[str]:
    """Второй рубеж: контекст с паттернами инструкции → честное «не найдено».

    Здоровый контекст (и ``None``) проходит без изменений.
    """
    if context and find_instruction_attacks(context):
        return CONTEXT_QUARANTINE_NOTICE
    return context