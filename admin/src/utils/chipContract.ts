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