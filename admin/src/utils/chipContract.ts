/**
 * Эмодзи-контракт статус-чипов админ-консоли.
 *
 * Канон: shared/patterns/documentation-emoji-contract.md (раздел
 * «Контракт статус-чипов UI») и ui-canon-property-map.md §3.
 * Единственный источник значков консоли: один эмодзи — одно понятие
 * во всём UI (чип, опция фильтра, экран «Справка → Обозначения»).
 *
 * HEALTH-семейство (канон): 🟢 успех · ❌ ошибка · ⚠️ предупреждение ·
 * 🔄 в работе · 🔁 повтор · 🚫 пропущено · ➖ нет данных.
 */

export type AiStatusKey =
  | "success"
  | "error"
  | "warning"
  | "running"
  | "retry"
  | "skipped"
  | "muted";

export interface AiChip {
  /** Эмодзи значка — единственный носитель уровня сигнала. */
  emoji: string;
  /** Человекочитаемая подпись (sentence case, UPPERCASE в чипах запрещён). */
  label: string;
}

export const STATUS_CHIP: Record<AiStatusKey, AiChip> = {
  success: { emoji: "🟢", label: "Успешно" },
  error: { emoji: "❌", label: "Ошибка" },
  warning: { emoji: "⚠️", label: "Предупреждение" },
  running: { emoji: "🔄", label: "В работе" },
  retry: { emoji: "🔁", label: "Повтор" },
  skipped: { emoji: "🚫", label: "Пропущено" },
  muted: { emoji: "➖", label: "Нет данных" },
};

/** Синонимы машинных статусов → ключ чипа (нормализация в одном месте). */
const STATUS_KEY_ALIASES: Record<string, AiStatusKey> = {
  success: "success",
  ok: "success",
  done: "success",
  completed: "success",
  error: "error",
  failed: "error",
  failure: "error",
  warning: "warning",
  warn: "warning",
  running: "running",
  started: "running",
  in_progress: "running",
  processing: "running",
  retry: "retry",
  skipped: "skipped",
};

export function statusChipKey(raw: string | null | undefined): AiStatusKey {
  const k = (raw ?? "").trim().toLowerCase();
  return STATUS_KEY_ALIASES[k] ?? "muted";
}

/**
 * Модальности operational-консоли (расширение контракта проектом AIP;
 * подписи совпадают с OPERATIONAL_MODALITY_LABEL из operationalConsoleUi).
 */
export const MODALITY_CHIP: Record<string, AiChip> = {
  text: { emoji: "💬", label: "Текст" },
  rag: { emoji: "📚", label: "RAG" },
  image: { emoji: "🖼️", label: "Изображение" },
  audio: { emoji: "🎧", label: "Аудио" },
  doc: { emoji: "📄", label: "Документ" },
  log: { emoji: "📜", label: "Прочее" },
  mem: { emoji: "🧠", label: "Память" },
  ocr: { emoji: "🔍", label: "OCR" },
  vision: { emoji: "👁️", label: "Vision" },
  test: { emoji: "🧪", label: "Тест" },
};

/**
 * Этапы конвейера (канон §3: значки без слов).
 * ✔︎ — U+2714 + U+FE0E (текстовый стиль, без цветной вариации).
 */
export type AiStageVariant =
  | "success"
  | "loading"
  | "processing"
  | "reset"
  | "warning"
  | "error"
  | "muted";

export const STAGE_CHIP: Record<AiStageVariant, string> = {
  success: "✔︎",
  loading: "🔄",
  processing: "🔄",
  reset: "↺",
  warning: "⚠️",
  error: "❌",
  muted: "➖",
};

/**
 * Собрать опцию фильтра: агрегатные пункты («все», «прочие») —
 * без значка, конкретные — с эмодзи того же понятия, что в чипе.
 */
export function chipOption(value: string, label: string): string {
  const chip = MODALITY_CHIP[value] ?? STATUS_CHIP[statusChipKey(value)];
  return chip ? `${chip.emoji} ${label}` : label;
}

/**
 * Тултип значка-флага — канон (эмодзи-контракт, правило 7):
 * слово-флаг в списке/таймлайне заменяется значком, при наведении
 * всплывает комментарий формата «Тип: Значение» («Статус: Одобрен»).
 */
export function flagTitle(type: string, value: string): string {
  return `${type}: ${value}`;
}

/* ===== B. Статусы источников (консоль допуска) ===== */

export type SourceStatusKey =
  | "approved"
  | "need_preview"
  | "preview_ready"
  | "patterns_changed"
  | "error";

export const SOURCE_STATUS_CHIP: Record<SourceStatusKey, AiChip> = {
  approved: { emoji: "✅", label: "Одобрен" },
  need_preview: { emoji: "👀", label: "Нужен preview" },
  preview_ready: { emoji: "📷", label: "Preview готов" },
  patterns_changed: { emoji: "✏️", label: "Есть изменения" },
  error: { emoji: "❌", label: "Ошибка" },
};

export function sourceStatusKey(raw: string | null | undefined): SourceStatusKey | "unknown" {
  const k = (raw ?? "").trim().toLowerCase();
  const known: SourceStatusKey[] = [
    "approved", "need_preview", "preview_ready", "patterns_changed", "error",
  ];
  return (known as string[]).includes(k) ? (k as SourceStatusKey) : "unknown";
}

/** Чип статуса допуска: неизвестный статус показывается как «Нужен preview». */
export function sourceStatusChip(raw: string | null | undefined): AiChip {
  const key = sourceStatusKey(raw);
  return SOURCE_STATUS_CHIP[key === "unknown" ? "need_preview" : key];
}

/* ===== C. Статусы индексации документов ===== */

export type DocIndexKey = "indexed" | "not_indexed" | "unknown";

export const DOC_INDEX_CHIP: Record<DocIndexKey, AiChip> = {
  indexed: { emoji: "✅", label: "В индексе" },
  not_indexed: { emoji: "⬜", label: "Не в индексе" },
  unknown: { emoji: "➖", label: "Нет данных" },
};

export function docIndexKey(chunkCount: number | null | undefined): DocIndexKey {
  if (chunkCount == null) return "unknown";
  return chunkCount > 0 ? "indexed" : "not_indexed";
}

/* ===== D. Флаги готовности (admin-status dot-чипы → значки) ===== */

export type FlagChipKey =
  | "active"
  | "inactive"
  | "fallback"
  | "off"
  | "builtin"
  | "ready"
  | "down"
  | "flag_unknown"
  | "empty"
  | "normal"
  | "degraded"
  | "pending";

export const FLAG_CHIP: Record<FlagChipKey, AiChip> = {
  active: { emoji: "⚡", label: "Активен" },
  inactive: { emoji: "⚪", label: "Неактивен" },
  fallback: { emoji: "🔀", label: "Резервный" },
  off: { emoji: "🚫", label: "Выключен" },
  builtin: { emoji: "📌", label: "Вшитый" },
  ready: { emoji: "✅", label: "Готов" },
  down: { emoji: "❌", label: "Недоступен" },
  flag_unknown: { emoji: "❓", label: "Неизвестно" },
  empty: { emoji: "📭", label: "Пуст" },
  normal: { emoji: "🟢", label: "Норма" },
  degraded: { emoji: "🟠", label: "Деградация" },
  pending: { emoji: "⚠️", label: "Ожидание" },
};

/* ===== E. Типы audit-событий ===== */

export const AUDIT_EVENT_CHIP: Record<string, AiChip> = {
  admin_login: { emoji: "🔑", label: "Вход в админку" },
  admin_action: { emoji: "🛠️", label: "Действие в админке" },
  site_visit: { emoji: "🌐", label: "Визит на сайт" },
  chat_request: { emoji: "💬", label: "Запрос чата" },
  rag_query: { emoji: "📚", label: "RAG-запрос" },
  provider_switch: { emoji: "🔀", label: "Смена провайдера" },
};

export function auditEventChip(eventType: string | null | undefined): AiChip | null {
  const k = (eventType ?? "").trim().toLowerCase();
  return AUDIT_EVENT_CHIP[k] ?? null;
}

/* ===== F. Видимость карточек проектов ===== */

export const VISIBILITY_CHIP: Record<"visible" | "hidden", AiChip> = {
  visible: { emoji: "⚡", label: "Видна на сайте" },
  hidden: { emoji: "⚪", label: "Скрыта" },
};