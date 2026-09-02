import { useEffect, useMemo, useRef, useState } from "react";
import {
  getExecutionSession,
  listExecutionSessions,
  type ExecutionSession,
  type ExecutionSessionDetail,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalModalityBadge } from "../components/OperationalModalityBadge";
import { OperationalPipelineStageIcon } from "../components/OperationalPipelineStageIcon";
import { StatusChip } from "../components/StatusChip";
import { chipOption } from "../utils/chipContract";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import {
  detailsJsonPreview,
  formatDetailsJson,
  operationalModalityFromRouteKey,
  pipelineStageVariant,
} from "../utils/operationalConsoleUi";
import {
  formatDurationMs,
  formatTimestampLocal,
  normalizeRouteKey,
  routeLabelRu,
  showLogsRouteLabelBesideModalityBadge,
  stageToActionRu,
  statusLabelRu,
} from "../utils/operationalLabels";

const PAGE_SIZE = 7;
const WINDOW_OPTIONS: Array<{ label: string; ms: number }> = [
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "48h", ms: 48 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

type RouteFilter = "all" | "text" | "rag" | "image" | "audio" | "document" | "other";
type StatusFilter = "all" | "ok" | "error" | "other";

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? id.slice(0, 8) + "…" : id;
}

function toTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const n = new Date(iso).getTime();
  return Number.isFinite(n) ? n : null;
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

function sessionPreview(session: ExecutionSession): string {
  const meta = session.metadata || {};
  return (
    String(meta.query || "").trim() ||
    String(meta.user_text || "").trim() ||
    String(meta.preview || "").trim() ||
    "—"
  );
}

function sessionWallDurationMs(session: ExecutionSession): number | null {
  const started = toTs(session.started_at);
  const finished = toTs(session.finished_at);
  if (started == null || finished == null) return session.duration_ms ?? null;
  return Math.max(0, finished - started);
}

function buildPipelineSummary(steps: ExecutionSessionDetail["steps"]): string {
  return steps.map((s) => stageToActionRu(s.stage_name)).join(" → ");
}

function detailLabels(routeKey: string): { left: string; right: string } {
  if (routeKey === "audio") {
    return { left: "Расшифровка речи (STT)", right: "Аудио-ответ / синтез речи (TTS)" };
  }
  if (routeKey === "image") {
    return { left: "Промпт генерации", right: "Обогащённый промпт / описание изображения" };
  }
  if (routeKey === "rag") {
    return { left: "RAG-запрос", right: "RAG-ответ / контекст retrieval" };
  }
  return { left: "Текст запроса", right: "Ответ модели" };
}

export function LogsPage() {
  const [sessions, setSessions] = useState<ExecutionSession[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<ExecutionSessionDetail | null>(null);
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [windowLabel, setWindowLabel] = useState("24h");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);

  const windowMs = useMemo(() => WINDOW_OPTIONS.find((x) => x.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms, [windowLabel]);

  const dateTo = useMemo(() => new Date().toISOString().slice(0, 10), [refreshNonce]);
  const dateFrom = useMemo(() => {
    const d = new Date(Date.now() - windowMs);
    return d.toISOString().slice(0, 10);
  }, [windowMs, refreshNonce]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await listExecutionSessions({
          route: routeFilter === "all" ? undefined : routeFilter,
          status: statusFilter === "all" ? undefined : statusFilter,
          date_from: dateFrom,
          date_to: dateTo,
          search: search.trim() || undefined,
          limit: PAGE_SIZE,
          offset: currentPage * PAGE_SIZE,
        });
        if (cancelled) return;
        setSessions(res.items);
        setTotal(res.total);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Не удалось загрузить логи");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentPage, routeFilter, statusFilter, dateFrom, dateTo, search, refreshNonce]);

  useEffect(() => {
    if (!sessions.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !sessions.some((s) => s.id === selectedId)) {
      setSelectedId(sessions[0].id);
    }
  }, [sessions, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDetail(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const detail = await getExecutionSession(selectedId);
        if (!cancelled) setSelectedDetail(detail);
      } catch (e) {
        if (!cancelled) setSelectedDetail(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshNonce]);

  const totalPagesRaw = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const lastPageIndex = totalPagesRaw - 1;

  function resetPagination() {
    pendingListFocusRef.current = true;
    setCurrentPage(0);
    const first = sessions[0];
    if (first) setSelectedId(first.id);
  }

  function goPrevPage() {
    pendingListFocusRef.current = true;
    setCurrentPage((p) => Math.max(0, p - 1));
  }

  function goNextPage() {
    pendingListFocusRef.current = true;
    setCurrentPage((p) => Math.min(lastPageIndex, p + 1));
  }

  useEffect(() => {
    if (!selectedId) return;
    const list = listRef.current;
    if (!list) return;
    const safeId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(selectedId)
        : selectedId.replace(/"/g, '\\"');
    const row = list.querySelector<HTMLButtonElement>(`[data-session-id="${safeId}"]`);
    if (!row) return;
    row.scrollIntoView({ block: "nearest" });
    const listHasFocus =
      document.activeElement instanceof Node && list.contains(document.activeElement);
    const shouldFocus = pendingListFocusRef.current || listHasFocus;
    pendingListFocusRef.current = false;
    if (!shouldFocus) return;
    const id = window.requestAnimationFrame(() => {
      row.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [selectedId, currentPage]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input") || t.closest("textarea") || t.closest("select") || t.isContentEditable)) {
        return;
      }
      if (!sessions.length) return;
      const curIdx = selectedId ? sessions.findIndex((s) => s.id === selectedId) : 0;
      if (curIdx < 0) return;
      const nextIdx =
        e.key === "ArrowDown"
          ? Math.min(sessions.length - 1, curIdx + 1)
          : Math.max(0, curIdx - 1);
      if (nextIdx === curIdx) return;
      e.preventDefault();
      const next = sessions[nextIdx];
      if (!next) return;
      pendingListFocusRef.current = true;
      setSelectedId(next.id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sessions, selectedId]);

  const selected = sessions.find((s) => s.id === selectedId) ?? null;
  const selectedRouteKey = selected ? normalizeRouteKey(selected.route) : "unknown";

  return (
    <div className="page logs-page">
      <div className="logs-page__header">
        <div>
          <h1 className="page__title">Логи</h1>
          <p className="page__lead logs-lead">
            Operational console · execution-сессии · время: местное
          </p>
        </div>
      </div>

      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : (
        <div className="logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row">
                <select
                  className="logs-select"
                  value={windowLabel}
                  onChange={(e) => {
                    setWindowLabel(e.target.value);
                    setCurrentPage(0);
                  }}
                  aria-label="Окно времени"
                >
                  {WINDOW_OPTIONS.map((w) => (
                    <option key={w.label} value={w.label}>
                      {w.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={routeFilter}
                  onChange={(e) => {
                    setRouteFilter(e.target.value as RouteFilter);
                    setCurrentPage(0);
                  }}
                  aria-label="Фильтр маршрута"
                >
                  {/* Опции фильтра — эмодзи из chipContract: значок
                      совпадает с чипом той же модальности. Агрегат
                      («все маршруты») — без значка. */}
                  <option value="all">все маршруты</option>
                  <option value="text">{chipOption("text", "текст")}</option>
                  <option value="rag">{chipOption("rag", "RAG")}</option>
                  <option value="image">{chipOption("image", "изображения")}</option>
                  <option value="audio">{chipOption("audio", "аудио")}</option>
                  <option value="document">{chipOption("doc", "документы")}</option>
                  <option value="other">прочее</option>
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value as StatusFilter);
                    setCurrentPage(0);
                  }}
                  aria-label="Фильтр статуса"
                >
                  <option value="all">все статусы</option>
                  <option value="ok">{chipOption("ok", "успешно")}</option>
                  <option value="error">{chipOption("error", "ошибка")}</option>
                  <option value="other">прочие</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setCurrentPage(0);
                }}
                placeholder="Поиск: provider, model, event_type, route..."
              />
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>
                  Страница {currentPage + 1} из {totalPagesRaw} · всего сессий: {total} · показано: {sessions.length}
                </span>
                <OperationalRefreshButton
                  loading={loading}
                  onClick={() => setRefreshNonce((n) => n + 1)}
                />
              </div>
              <div className="logs-page-controls">
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goPrevPage}
                  disabled={currentPage <= 0 || loading}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goNextPage}
                  disabled={currentPage >= lastPageIndex || loading}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={resetPagination}
                  disabled={currentPage === 0}
                >
                  Сброс
                </button>
              </div>
            </div>

            <div className="logs-list" ref={listRef}>
              {loading && sessions.length === 0 ? (
                <Loading />
              ) : sessions.length === 0 ? (
                <EmptyState message="За выбранный период сессии не найдены." />
              ) : (
                sessions.map((s) => {
                  const routeKey = normalizeRouteKey(s.route);
                  const status = normalizeStatus(s.status);
                  const wallMs = sessionWallDurationMs(s);
                  const preview = sessionPreview(s);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      data-session-id={s.id}
                      className={`logs-item ${selectedId === s.id ? "logs-item--selected" : ""}`}
                      onClick={() => {
                        pendingListFocusRef.current = true;
                        setSelectedId(s.id);
                      }}
                    >
                      <div className="logs-item__row logs-item__row--tight">
                        <span className="mono logs-item__ts">{formatTimestampLocal(s.created_at)}</span>
                        <OperationalModalityBadge modality={operationalModalityFromRouteKey(routeKey)} />
                        {/* Подписи sentence case — UPPERCASE в чипах
                            запрещён контрактом. */}
                        <span className="logs-item__route-status">
                          {showLogsRouteLabelBesideModalityBadge(routeKey) ? (
                            <>
                              {routeLabelRu(routeKey)} ·{" "}
                            </>
                          ) : null}
                          {statusLabelRu(status)}
                        </span>
                      </div>
                      <div className="logs-item__preview">{preview || "—"}</div>
                      <div className="logs-item__row logs-item__meta muted">
                        <span className="mono" title={s.id}>
                          {shortId(s.id)}
                        </span>
                        <span title="visitor_id">{s.visitor_id ? shortId(s.visitor_id) : "н/д"}</span>
                        <span title="IP-адрес">{s.client_ip ?? "н/д"}</span>
                        <span title="Общая длительность">{formatDurationMs(wallMs)}</span>
                        <span className="mono truncate" title={s.provider_key || ""}>
                          {s.provider_key || "н/д"}
                        </span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите сессию для трассировки execution." />
            ) : !selectedDetail ? (
              <Loading />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <div>
                    <h2 className="card__title logs-detail__title">Трассировка execution-сессии</h2>
                  </div>
                  <StatusChip status={selected.status} label={statusLabelRu(selected.status)} />
                </div>

                <div className="logs-summary-grid">
                  <div className="logs-summary-col">
                    <h3 className="memory-summary-col__title">Параметры сессии</h3>
                    <dl className="kv logs-detail-kv">
                      <dt>execution_id</dt>
                      <dd className="mono break-all">{selected.id}</dd>
                      <dt>visitor_id</dt>
                      <dd className="mono break-all">{selected.visitor_id ?? "—"}</dd>
                      <dt>IP-адрес</dt>
                      <dd className="mono">{selected.client_ip ?? "—"}</dd>
                      <dt>session_id</dt>
                      <dd className="mono break-all">{selected.session_id ?? "—"}</dd>
                      <dt>route</dt>
                      <dd className="mono">{selected.route}</dd>
                    </dl>
                  </div>
                  <div className="logs-summary-col">
                    <h3 className="memory-summary-col__title">Параметры исполнения</h3>
                    <dl className="kv logs-detail-kv">
                      <dt>Статус</dt>
                      <dd>
                        <StatusChip status={selected.status} label={statusLabelRu(selected.status)} />
                      </dd>
                      <dt>provider / model</dt>
                      <dd className="mono">
                        {selected.provider_key ?? "—"} / {selected.model_name ?? "—"}
                      </dd>
                      <dt>Начало</dt>
                      <dd className="mono">{formatTimestampLocal(selected.started_at)}</dd>
                      <dt>Завершение</dt>
                      <dd className="mono">{formatTimestampLocal(selected.finished_at)}</dd>
                      <dt>Общая длительность</dt>
                      <dd>{formatDurationMs(sessionWallDurationMs(selected))}</dd>
                    </dl>
                  </div>
                </div>

                <div className="logs-pipeline">
                  <div className="logs-pipeline__label muted">Цепочка этапов</div>
                  <div className="logs-pipeline__flow" title={buildPipelineSummary(selectedDetail.steps)}>
                    {buildPipelineSummary(selectedDetail.steps) || "—"}
                  </div>
                </div>

                <div className="logs-detail-grid page__mt logs-detail-grid--dense">
                  <div className="logs-detail-block">
                    <h3 className="logs-detail-block__title">{detailLabels(selectedRouteKey).left}</h3>
                    <pre className="logs-pre mono">{String(selected.metadata?.query ?? "—")}</pre>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="logs-detail-block__title">{detailLabels(selectedRouteKey).right}</h3>
                    <pre className="logs-pre mono">{String(selected.metadata?.response ?? "—")}</pre>
                    {(() => {
                      const rawSources = selected.metadata?.sources;
                      const sources = Array.isArray(rawSources) ? rawSources.map(String) : [];
                      if (sources.length === 0) return null;
                      return (
                        <div className="logs-response-sources">
                          <span className="logs-response-sources__divider" />
                          <span className="logs-response-sources__label">Источники:</span>
                          {sources.join(", ")}
                        </div>
                      );
                    })()}
                  </div>
                </div>

                {selected.metadata?.error ? (
                  <div className="logs-detail-block logs-detail-block--error">
                    <h3 className="logs-detail-block__title">ОШИБКА</h3>
                    <pre className="logs-pre mono">{String(selected.metadata.error)}</pre>
                  </div>
                ) : null}

                <h3 className="logs-timeline-heading">
                  Таймлайн pipeline
                  {selected.is_backfilled ? (
                    <span className="logs-timeline-hint" title="Сессия создана автоматически из архивных operational logs. Длительности и интервалы между этапами приблизительные.">
                      приблизительный
                    </span>
                  ) : null}
                </h3>
                <div className="logs-timeline">
                  {selectedDetail.steps.map((step, i) => {
                    const prev = i > 0 ? toTs(selectedDetail.steps[i - 1].created_at) : null;
                    const cur = toTs(step.created_at);
                    const delta = prev != null && cur != null ? Math.max(0, cur - prev) : null;
                    const stageRaw = String(step.stage_name ?? "").trim();
                    const label = stageToActionRu(step.stage_name);
                    return (
                      <div
                        key={step.id}
                        className="logs-stage logs-stage--compact"
                        title={stageRaw ? `stage: ${stageRaw}` : undefined}
                      >
                        <div className="logs-stage__top">
                          <span className="mono logs-stage__time">
                            {formatTimestampLocal(step.created_at)}
                          </span>
                          <span className="logs-stage__label af-logs-stage-label-with-icon">
                            <OperationalPipelineStageIcon
                              variant={pipelineStageVariant(stageRaw, step.status)}
                            />
                            {label}
                          </span>
                          <StatusChip status={step.status} label={statusLabelRu(step.status)} />
                          {step.duration_ms != null ? (
                            <span className="muted mono" title="Длительность выполнения шага">
                              {formatDurationMs(step.duration_ms)}
                            </span>
                          ) : null}
                          {delta != null ? (
                            <span
                              className="muted mono logs-stage__delta"
                              title="Время, прошедшее с предыдущего шага"
                            >
                              +{delta} мс
                            </span>
                          ) : null}
                        </div>
                        <details className="logs-stage__details">
                          <summary className="log-details__summary">
                            {detailsJsonPreview(step.metadata)}
                          </summary>
                          <pre className="log-details__json mono">
                            {formatDetailsJson(step.metadata)}
                          </pre>
                        </details>
                      </div>
                    );
                  })}
                </div>

                <SessionJsonSnapshot
                  className="page__mt"
                  body={JSON.stringify(selectedDetail, null, 2)}
                />
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
