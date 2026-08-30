/**
 * Operational display labels for logs / lifecycle.
 */

export const LOCAL_TIME_NOTE = "время: местное";

/* Форматтеры времени в местной зоне зрителя (решение владельца 30.08.2026 —
   «местное, а не московское принудительно»). Бэкенд отдаёт наивные UTC-строки
   (PG Etc/UTC, без суффикса зоны), поэтому перед форматированием строка
   нормализуется: время без смещения считается UTC (суффикс «Z»), иначе
   браузер вне UTC прочитал бы время неверно. */

const LOCAL_FORMAT_FULL = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const LOCAL_FORMAT_DATE = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const LOCAL_FORMAT_SHORT = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const NAIVE_DATETIME_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function normalizeIsoTimestamp(raw: string): string {
  let s = raw.trim().replace(" ", "T").toUpperCase();
  if (NAIVE_DATETIME_RE.test(s)) {
    // микросекунды усекаем до миллисекунд: Date.parse надёжен на 3 знаках
    s = s.replace(/(\.\d{3})\d+$/, "$1");
    return s + "Z";
  }
  return s;
}

function parseTimestampMs(isoOrMs: string | number | null | undefined): number | null {
  if (isoOrMs == null) return null;
  if (typeof isoOrMs === "number") {
    return Number.isFinite(isoOrMs) ? isoOrMs : null;
  }
  const raw = isoOrMs.trim();
  if (!raw || DATE_ONLY_RE.test(raw)) return null; // дата без времени — не момент
  const ms = Date.parse(normalizeIsoTimestamp(raw));
  return Number.isFinite(ms) ? ms : null;
}

const STAGE_NAME_RU: Record<string, string> = {
  session_resolve: "Получен запрос",
  route_selected: "Определён тип запроса",
  memory_load: "Загрузка памяти (диалог)",
  memory_load_started: "Загрузка памяти (диалог) начата",
  memory_load_done: "Память диалога загружена",
  memory_append_done: "Реплики диалога сохранены в память",
  cache_check: "Проверка кеша",
  rag_search: "RAG-поиск",
  prompt_build: "Формирование промпта",
  provider_select: "Выбор AI-провайдера",
  provider_switch: "Переключение AI-провайдера",
  llm_call: "Вызов LLM",
  memory_save: "Сохранение в память",
  log_write: "Запись operational log",
  response_return: "Возврат ответа",
  processing_done: "Обработка завершена",
  processing_error: "Ошибка обработки",
};

const ROUTE_LABEL_RU: Record<string, string> = {
  rag: "RAG",
  text: "Текст",
  image: "Генерация изображений",
  audio: "Аудио",
  document: "Документ",
  log: "Прочее",
  unknown: "Прочее",
};

const STATUS_RU: Record<string, string> = {
  success: "успешно",
  error: "ошибка",
  skipped: "пропущено",
  retry: "повтор",
  started: "запущено",
  warning: "предупреждение",
  failed: "ошибка",
};

const EVENT_TYPE_RU: Record<string, string> = {
  chat_request: "Запрос чата",
  rag_query: "RAG-запрос",
  provider_switch: "Переключение провайдера",
  admin_login: "Вход в админку",
  site_visit: "Посещение сайта",
  admin_action: "Админ-действие",
};

export function normalizeMachineStage(stage: string | null | undefined): string {
  let s = String(stage ?? "").trim();
  if (!s) return "";
  s = s.replace(/﻿/g, "").replace(/[​-‍]/g, "");
  try {
    s = s.normalize("NFKC");
  } catch {
    /* ignore */
  }
  return s.toLowerCase().replace(/\s+/g, "_");
}

export function normalizeRouteKey(route: string | null | undefined): string {
  const raw = (route || "").trim().toLowerCase();
  if (!raw) return "unknown";
  if (raw === "rag" || raw === "rag_response") return "rag";
  if (raw === "text" || raw === "text_response") return "text";
  if (raw === "image" || raw === "image_generation" || raw === "image_response") return "image";
  if (raw === "audio" || raw === "voice" || raw === "voice_response") return "audio";
  if (raw === "document" || raw === "documents") return "document";
  return "unknown";
}

export function routeLabelRu(route: string | null | undefined): string {
  return ROUTE_LABEL_RU[normalizeRouteKey(route)] ?? route ?? "—";
}

export function statusLabelRu(raw: string | null | undefined): string {
  if (!raw) return "—";
  return STATUS_RU[raw.trim().toLowerCase()] ?? raw;
}

export function eventTypeLabelRu(raw: string | null | undefined): string {
  if (!raw) return "—";
  return EVENT_TYPE_RU[raw.trim().toLowerCase()] ?? raw;
}

export function stageToActionRu(stage: string | null | undefined, _details?: unknown): string {
  const raw = (stage || "").trim();
  if (!raw) return "—";
  const rawKey = normalizeMachineStage(raw);
  const mapped = STAGE_NAME_RU[rawKey];
  if (mapped) return mapped;
  if (rawKey.endsWith("_done")) return `${raw.replace(/_/g, " ")} завершён`;
  if (rawKey.endsWith("_error")) return `Ошибка ${raw.replace(/_/g, " ")}`;
  if (rawKey.endsWith("_started")) return `${raw.replace(/_/g, " ")} запущен`;
  return raw.replace(/_/g, " ");
}

/** Полная метка времени в местной зоне зрителя: «30.08.2026 10:40:59». */
export function formatTimestampLocal(isoOrMs: string | number | null | undefined): string {
  const ms = parseTimestampMs(isoOrMs);
  if (ms != null) {
    return LOCAL_FORMAT_FULL.format(new Date(ms)).replace(",", "");
  }
  // дата без времени — не момент: показываем день как есть (dd.mm.yyyy)
  if (typeof isoOrMs === "string" && DATE_ONLY_RE.test(isoOrMs.trim())) {
    return isoOrMs.trim().split("-").reverse().join(".");
  }
  return "—";
}

/** Дата (день) в местной зоне зрителя: «30.08.2026». */
export function formatDateLocal(isoOrMs: string | number | null | undefined): string {
  const ms = parseTimestampMs(isoOrMs);
  if (ms != null) {
    return LOCAL_FORMAT_DATE.format(new Date(ms));
  }
  if (typeof isoOrMs === "string" && DATE_ONLY_RE.test(isoOrMs.trim())) {
    return isoOrMs.trim().split("-").reverse().join(".");
  }
  return "—";
}

/** Короткая метка «день · часы:минуты» в местной зоне: «30.08 · 10:40». */
export function formatShortDateTimeLocal(isoOrMs: string | number | null | undefined): string {
  const ms = parseTimestampMs(isoOrMs);
  if (ms == null) return "—";
  return LOCAL_FORMAT_SHORT.format(new Date(ms)).replace(",", "");
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toFixed(2)} с`;
}

export function showLogsRouteLabelBesideModalityBadge(routeKey: string | null | undefined): boolean {
  return normalizeRouteKey(routeKey) !== "document";
}
