/**
 * Operational display labels for logs / lifecycle.
 */

export const MSK_TIMEZONE = "Europe/Moscow";

const EVENT_TYPE_RU: Record<string, string> = {
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

export function stageToActionRu(stage: string | null | undefined, _details?: unknown): string {
  const raw = (stage || "").trim();
  if (!raw) return "—";
  const rawKey = normalizeMachineStage(raw);
  const mapped = EVENT_TYPE_RU[rawKey];
  if (mapped) return mapped;
  if (rawKey.endsWith("_done")) return `${raw.replace(/_/g, " ")} завершён`;
  if (rawKey.endsWith("_error")) return `Ошибка ${raw.replace(/_/g, " ")}`;
  if (rawKey.endsWith("_started")) return `${raw.replace(/_/g, " ")} запущен`;
  return raw.replace(/_/g, " ");
}

export function formatTimestampMsk(isoOrMs: string | number | null | undefined): string {
  if (isoOrMs == null) return "—";
  const ms = typeof isoOrMs === "number" ? isoOrMs : new Date(isoOrMs).getTime();
  if (!Number.isFinite(ms)) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: MSK_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(new Date(ms))
    .replace(",", "");
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toFixed(2)} с`;
}

export function sessionWallDurationMs(timestampsMs: number[]): number | null {
  const finite = timestampsMs.filter((t) => Number.isFinite(t));
  if (finite.length < 2) return null;
  const t0 = Math.min(...finite);
  const t1 = Math.max(...finite);
  return Math.max(0, t1 - t0);
}

export function sessionMaxStepLatencyMs(
  detailsList: Array<Record<string, unknown> | null>
): number | null {
  let best: number | null = null;
  for (const d of detailsList) {
    if (!d) continue;
    for (const key of ["latency_ms", "response_time_ms", "duration_ms"] as const) {
      const v = d[key];
      if (v == null) continue;
      const n = Number(v);
      if (Number.isFinite(n)) {
        best = best == null ? n : Math.max(best, n);
      }
    }
  }
  return best != null ? Math.round(best) : null;
}

export function sessionAvgStepLatencyMs(
  detailsList: Array<Record<string, unknown> | null>
): number | null {
  const vals: number[] = [];
  for (const d of detailsList) {
    if (!d) continue;
    for (const key of ["latency_ms", "response_time_ms", "duration_ms"] as const) {
      const v = d[key];
      if (v == null) continue;
      const n = Number(v);
      if (Number.isFinite(n)) {
        vals.push(n);
        break;
      }
    }
  }
  if (!vals.length) return null;
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
}

export function showLogsRouteLabelBesideModalityBadge(routeKey: string | null | undefined): boolean {
  return normalizeRouteKey(routeKey) !== "document";
}
