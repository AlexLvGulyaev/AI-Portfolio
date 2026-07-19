import { useEffect, useMemo, useRef, useState } from "react";
import {
  getExecutionSession,
  listExecutionSessions,
  listLogs,
  type ExecutionSession,
  type ExecutionSessionDetail,
  type OperationalLog,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalModalityBadge } from "../components/OperationalModalityBadge";
import { OperationalPipelineStageIcon } from "../components/OperationalPipelineStageIcon";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import {
  detailsJsonPreview,
  formatDetailsJson,
  operationalModalityFromRouteKey,
  pipelineStageVariant,
} from "../utils/operationalConsoleUi";
import {
  eventTypeLabelRu,
  formatDurationMs,
  formatTimestampMsk,
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
type AuditEventTypeFilter = "all" | "admin_login" | "site_visit" | "provider_switch" | "other";
type LogsTab = "execution" | "audit";

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
  const [activeTab, setActiveTab] = useState<LogsTab>("execution");

  // Audit logs state
  const [auditLogs, setAuditLogs] = useState<OperationalLog[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(0);
  const [auditEventType, setAuditEventType] = useState<AuditEventTypeFilter>("all");
  const [auditStatus, setAuditStatus] = useState<StatusFilter>("all");
  const [selectedAuditId, setSelectedAuditId] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);
  const auditListRef = useRef<HTMLDivElement | null>(null);
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
    if (activeTab !== "audit") return;
    let cancelled = false;
    (async () => {
      setAuditLoading(true);
      setAuditError(null);
      try {
        const params: Parameters<typeof listLogs>[0] = {
          date_from: dateFrom,
          date_to: dateTo,
          limit: PAGE_SIZE,
          offset: auditPage * PAGE_SIZE,
        };
        if (auditEventType !== "all") {
          params.event_type = auditEventType;
        }
        if (auditStatus !== "all") {
          params.status = auditStatus;
        }
        const res = await listLogs(params);
        if (cancelled) return;
        setAuditLogs(res.items);
        setAuditTotal(res.total);
      } catch (e) {
        if (!cancelled) setAuditError(e instanceof Error ? e.message : "Не удалось загрузить audit-логи");
      } finally {
        if (!cancelled) setAuditLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeTab, auditPage, auditEventType, auditStatus, dateFrom, dateTo, refreshNonce]);

  useEffect(() => {
    if (!auditLogs.length) {
      setSelectedAuditId(null);
      return;
    }
    if (!selectedAuditId || !auditLogs.some((l) => l.id === selectedAuditId)) {
      setSelectedAuditId(auditLogs[0].id);
    }
  }, [auditLogs, selectedAuditId]);

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
  const selectedStatus = selected ? normalizeStatus(selected.status) : "other";

  const totalAuditPagesRaw = Math.max(1, Math.ceil(auditTotal / PAGE_SIZE));
  const lastAuditPageIndex = totalAuditPagesRaw - 1;

  function resetAuditPagination() {
    setAuditPage(0);
  }

  function goPrevAuditPage() {
    setAuditPage((p) => Math.max(0, p - 1));
  }

  function goNextAuditPage() {
    setAuditPage((p) => Math.min(lastAuditPageIndex, p + 1));
  }

  const selectedAuditLog = auditLogs.find((l) => l.id === selectedAuditId) ?? null;

  return (
    <div className="page logs-page">
      <div className="logs-page__header">
        <div>
          <h1 className="page__title">Логи</h1>
          <p className="page__lead logs-lead">
            Operational console · время: МСК · аудит: /admin/login и /track-visit
          </p>
        </div>
        <div className="admin-tabs logs-tabs">
          <button
            type="button"
            className={`admin-tab ${activeTab === "execution" ? "admin-tab--active" : ""}`}
            onClick={() => {
              setActiveTab("execution");
              setError(null);
            }}
          >
            Execution-сессии
          </button>
          <button
            type="button"
            className={`admin-tab ${activeTab === "audit" ? "admin-tab--active" : ""}`}
            onClick={() => {
              setActiveTab("audit");
              setAuditError(null);
            }}
          >
            Аудит
          </button>
        </div>
      </div>

      {activeTab === "execution" && error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : activeTab === "execution" ? (
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
                  <option value="all">все маршруты</option>
                  <option value="text">text</option>
                  <option value="rag">rag</option>
                  <option value="image">image</option>
                  <option value="audio">audio</option>
                  <option value="document">документ</option>
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
                  <option value="ok">ok</option>
                  <option value="error">error</option>
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
                        <span className="mono logs-item__ts">{formatTimestampMsk(s.created_at)}</span>
                        <OperationalModalityBadge modality={operationalModalityFromRouteKey(routeKey)} />
                        <span className="logs-item__route-status">
                          {showLogsRouteLabelBesideModalityBadge(routeKey) ? (
                            <>
                              {routeLabelRu(routeKey).toUpperCase()} ·{" "}
                            </>
                          ) : null}
                          {statusLabelRu(status).toUpperCase()}
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
                    <p className="logs-detail__sub muted">Время: МСК</p>
                  </div>
                  <span className={`logs-status logs-status--${selectedStatus}`}>
                    {statusLabelRu(selected.status).toUpperCase()}
                  </span>
                </div>

                <div className="logs-detail__route-line">
                  {showLogsRouteLabelBesideModalityBadge(selectedRouteKey) ? (
                    <>
                      {routeLabelRu(selectedRouteKey).toUpperCase()} ·{" "}
                    </>
                  ) : null}
                  {statusLabelRu(selected.status).toUpperCase()}
                </div>

                <div className="logs-summary-grid">
                  <div className="logs-summary-col">
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
                    <dl className="kv logs-detail-kv">
                      <dt>Статус</dt>
                      <dd>
                        <span className={`logs-status logs-status--${selectedStatus}`}>
                          {statusLabelRu(selected.status)}
                        </span>
                      </dd>
                      <dt>provider / model</dt>
                      <dd className="mono">
                        {selected.provider_key ?? "—"} / {selected.model_name ?? "—"}
                      </dd>
                      <dt>Начало</dt>
                      <dd className="mono">{formatTimestampMsk(selected.started_at)}</dd>
                      <dt>Завершение</dt>
                      <dd className="mono">{formatTimestampMsk(selected.finished_at)}</dd>
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
                    const status = normalizeStatus(step.status);
                    return (
                      <div
                        key={step.id}
                        className="logs-stage logs-stage--compact"
                        title={stageRaw ? `stage: ${stageRaw}` : undefined}
                      >
                        <div className="logs-stage__top">
                          <span className="mono logs-stage__time">
                            {formatTimestampMsk(step.created_at)}
                          </span>
                          <span className="logs-stage__label af-logs-stage-label-with-icon">
                            <OperationalPipelineStageIcon
                              variant={pipelineStageVariant(stageRaw, step.status)}
                            />
                            {label}
                          </span>
                          <span className={`logs-status logs-status--${status}`}>
                            {statusLabelRu(step.status)}
                          </span>
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
      ) : auditError ? (
        <div className="panel panel--error page__mt" role="alert">
          {auditError}
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
                    setAuditPage(0);
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
                  value={auditEventType}
                  onChange={(e) => {
                    setAuditEventType(e.target.value as AuditEventTypeFilter);
                    setAuditPage(0);
                  }}
                  aria-label="Тип события"
                >
                  <option value="all">все события</option>
                  <option value="admin_login">admin_login</option>
                  <option value="site_visit">site_visit</option>
                  <option value="provider_switch">provider_switch</option>
                  <option value="other">прочее</option>
                </select>
                <select
                  className="logs-select"
                  value={auditStatus}
                  onChange={(e) => {
                    setAuditStatus(e.target.value as StatusFilter);
                    setAuditPage(0);
                  }}
                  aria-label="Фильтр статуса"
                >
                  <option value="all">все статусы</option>
                  <option value="ok">ok</option>
                  <option value="error">error</option>
                  <option value="other">прочие</option>
                </select>
              </div>
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>
                  Страница {auditPage + 1} из {totalAuditPagesRaw} · всего записей: {auditTotal} · показано: {auditLogs.length}
                </span>
                <OperationalRefreshButton
                  loading={auditLoading}
                  onClick={() => setRefreshNonce((n) => n + 1)}
                />
              </div>
              <div className="logs-page-controls">
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goPrevAuditPage}
                  disabled={auditPage <= 0 || auditLoading}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goNextAuditPage}
                  disabled={auditPage >= lastAuditPageIndex || auditLoading}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={resetAuditPagination}
                  disabled={auditPage === 0}
                >
                  Сброс
                </button>
              </div>
            </div>

            <div className="logs-list" ref={auditListRef}>
              {auditLoading && auditLogs.length === 0 ? (
                <Loading />
              ) : auditLogs.length === 0 ? (
                <EmptyState message="За выбранный период audit-записи не найдены." />
              ) : (
                auditLogs.map((log) => {
                  const status = normalizeStatus(log.status);
                  const meta = log.metadata || {};
                  const preview =
                    log.event_type === "admin_login"
                      ? `${meta.ip ?? "—"} · ${meta.user_agent ?? "—"}`
                      : log.event_type === "site_visit"
                      ? `${log.query ?? "—"} · ${meta.visitor_id ?? "—"}`
                      : log.event_type === "provider_switch"
                      ? `${log.provider_key ?? "—"} · ${log.model_name ?? "—"}`
                      : String(log.query ?? "").trim() || "—";
                  return (
                    <button
                      key={log.id}
                      type="button"
                      data-audit-id={log.id}
                      className={`logs-item ${selectedAuditId === log.id ? "logs-item--selected" : ""}`}
                      onClick={() => setSelectedAuditId(log.id)}
                    >
                      <div className="logs-item__row logs-item__row--tight">
                        <span className="mono logs-item__ts">{formatTimestampMsk(log.created_at)}</span>
                        <span className={`admin-status admin-status--${status === "error" ? "error" : "ok"}`}>
                          {eventTypeLabelRu(log.event_type)}
                        </span>
                        <span className="logs-item__route-status">{statusLabelRu(status).toUpperCase()}</span>
                      </div>
                      <div className="logs-item__preview">{preview}</div>
                      <div className="logs-item__row logs-item__meta muted">
                        <span className="mono" title={log.id}>{shortId(log.id)}</span>
                        <span className="mono" title="source">{log.source ?? "н/д"}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="logs-right card">
            {!selectedAuditLog ? (
              <EmptyState message="Выберите audit-запись для просмотра." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <div>
                    <h2 className="card__title logs-detail__title">Audit-запись</h2>
                    <p className="logs-detail__sub muted">{selectedAuditLog.id}</p>
                  </div>
                  <span className={`logs-status logs-status--${normalizeStatus(selectedAuditLog.status)}`}>
                    {statusLabelRu(selectedAuditLog.status).toUpperCase()}
                  </span>
                </div>

                <div className="logs-summary-grid">
                  <div className="logs-summary-col">
                    <dl className="kv logs-detail-kv">
                      <dt>event_type</dt>
                      <dd className="mono">{selectedAuditLog.event_type}</dd>
                      <dt>Тип события</dt>
                      <dd>{eventTypeLabelRu(selectedAuditLog.event_type)}</dd>
                      <dt>source</dt>
                      <dd className="mono">{selectedAuditLog.source ?? "—"}</dd>
                      <dt>status</dt>
                      <dd className="mono">{selectedAuditLog.status}</dd>
                    </dl>
                  </div>
                  <div className="logs-summary-col">
                    <dl className="kv logs-detail-kv">
                      <dt>Создано</dt>
                      <dd className="mono">{formatTimestampMsk(selectedAuditLog.created_at)}</dd>
                      <dt>query</dt>
                      <dd className="mono break-all">{selectedAuditLog.query ?? "—"}</dd>
                      <dt>response</dt>
                      <dd className="mono break-all">{selectedAuditLog.response ?? "—"}</dd>
                      <dt>error_message</dt>
                      <dd className="mono break-all">{selectedAuditLog.error_message ?? "—"}</dd>
                    </dl>
                  </div>
                </div>

                <div className="logs-detail-block page__mt">
                  <h3 className="logs-detail-block__title">Metadata</h3>
                  <pre className="logs-pre mono">{formatDetailsJson(selectedAuditLog.metadata)}</pre>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
