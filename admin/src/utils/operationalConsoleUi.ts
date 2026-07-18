/**
 * Shared operational-console UI contract.
 * Adapted from Assistant Flow admin-ui.
 */

export type OperationalModality =
  | "rag"
  | "mem"
  | "text"
  | "ocr"
  | "vision"
  | "audio"
  | "image"
  | "test"
  | "doc"
  | "log";

export type AfPipelineStageVariant =
  | "success"
  | "loading"
  | "processing"
  | "reset"
  | "warning"
  | "error"
  | "muted";

export const OPERATIONAL_MODALITY_LABEL: Record<OperationalModality, string> = {
  rag: "rag",
  mem: "mem",
  text: "text",
  ocr: "ocr",
  vision: "vision",
  audio: "audio",
  image: "image",
  test: "test",
  doc: "doc",
  log: "log",
};

export function operationalModalityBadgeClassList(mod: OperationalModality): string {
  return `mini-badge mini-badge--af mini-badge--af-${mod}`;
}

export function normalizeOperationalModality(raw: string): OperationalModality {
  const k = raw.trim().toLowerCase();
  const known: OperationalModality[] = [
    "rag", "mem", "text", "ocr", "vision", "audio", "image", "test", "doc", "log",
  ];
  if (known.includes(k as OperationalModality)) return k as OperationalModality;
  if (k === "memory") return "mem";
  if (k === "img" || k === "images") return "image";
  if (k === "voice") return "audio";
  if (k === "document" || k === "documents") return "doc";
  return "log";
}

export function operationalModalityFromRouteKey(routeKey: string): OperationalModality {
  const r = (routeKey || "").trim().toLowerCase();
  if (!r) return "log";
  if (r === "document" || r === "documents") return "doc";
  if (r === "rag" || r === "rag_response") return "rag";
  if (r === "text") return "text";
  if (r === "vision_ocr" || r === "ocr") return "ocr";
  if (r.includes("vision") || r === "image_analysis") return "vision";
  if (r.includes("audio") || r.includes("voice") || r.includes("stt") || r.includes("tts"))
    return "audio";
  if (r.includes("image") || r === "image_generation") return "image";
  if (r === "test" || r.includes("smoke")) return "test";
  return "log";
}

export function detailsJsonPreview(d: unknown): string {
  if (d == null) return "пусто";
  if (typeof d === "string") return d.length > 56 ? `${d.slice(0, 56)}…` : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 56 ? `${s.slice(0, 56)}…` : s || "{}";
  } catch {
    return "?";
  }
}

export function formatDetailsJson(d: unknown): string {
  if (d == null) return "null";
  if (typeof d === "string") return d;
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(d);
  }
}

export function pipelineStageVariant(
  stage: string,
  status?: string | null
): AfPipelineStageVariant {
  const s = (stage || "").toLowerCase();
  const st = (status || "").trim().toLowerCase();
  if (
    st === "error" ||
    st === "failed" ||
    s.includes("error") ||
    s.endsWith("_error") ||
    s.includes("failure")
  ) {
    return "error";
  }
  if (st === "warning" || s.includes("warn")) return "warning";
  if (s.includes("clear") || s.includes("reset") || s.includes("cleared")) return "reset";
  if (
    s.includes("_started") ||
    s.endsWith("started") ||
    s.includes("loading") ||
    s.includes("queued") ||
    s.includes("pending")
  ) {
    return "loading";
  }
  if (
    s.includes("_done") ||
    s.includes("completed") ||
    s.includes("success") ||
    st === "success" ||
    st === "ok"
  ) {
    return "success";
  }
  if (
    s.includes("processing") ||
    s.includes("append") ||
    s.includes("retrieve") ||
    s.includes("embedding") ||
    s.startsWith("memory_meta")
  ) {
    return "processing";
  }
  return "muted";
}
