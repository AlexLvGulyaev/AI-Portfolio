import { useEffect, useMemo, useState } from "react";
import { listLogs, type OperationalLog } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { formatDetailsJson } from "../utils/operationalConsoleUi";
import {
  eventTypeLabelRu,
  formatTimestampLocal,
  statusLabelRu,
} from "../utils/operationalLabels";

const PAGE_SIZE = 7;
const WINDOW_OPTIONS: Array<{ label: string; ms: number }> = [
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "48h", ms: 48 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

type StatusFilter = "all" | "ok" | "error" | "other";
type AuditEventTypeFilter =
  | "all"
  | "admin_login"
  | "admin_action"
  | "site_visit"
  | "provider_switch"
  | "other";

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? id.slice(0, 8) + "…" : id;
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

/* Аудит — отдельная консоль (вынесено из «Логов», решение владельца 30.08.2026):
   события admin_login / admin_action / site_visit / provider_switch из operational_logs,
   слева список, справа карточка записи. */
export function AuditPage() {
  const [auditLogs, setAuditLogs] = useState<OperationalLog[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(0);
  const [auditEventType, setAuditEventType] = useState<AuditEventTypeFilter>("all");
  const [auditStatus, setAuditStatus] = useState<StatusFilter>("all");
  const [windowLabel, setWindowLabel] = useState("24h");
  const [selectedAuditId, setSelectedAuditId] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  const windowMs = useMemo(
    () => WINDOW_OPTIONS.find((x) => x.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms,
    [windowLabel],
  );

  const dateTo = useMemo(() => new Date().toISOString().slice(0, 10), [refreshNonce]);
  const dateFrom = useMemo(() => {
    const d = new Date(Date.now() - windowMs);
    return d.toISOString().slice(0, 10);
  }, [windowMs, refreshNonce]);

  useEffect(() => {
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
        if (!cancelled) setAuditError(e instanceof Error ? e.message : "Не удалось загрузить audit-записи");
      } finally {
        if (!cancelled) setAuditLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auditPage, auditEventType, auditStatus, dateFrom, dateTo, refreshNonce]);

  useEffect(() => {
    if (!auditLogs.length) {
      setSelectedAuditId(null);
      return;
    }
    if (!selectedAuditId || !auditLogs.some((l) => l.id === selectedAuditId)) {
      setSelectedAuditId(auditLogs[0].id);
    }
  }, [auditLogs, selectedAuditId]);

  const totalAuditPagesRaw = Math.max(1, Math.ceil(auditTotal / PAGE_SIZE));
  const lastAuditPageIndex = totalAuditPagesRaw - 1;

  const selectedAuditLog = auditLogs.find((l) => l.id === selectedAuditId) ?? null;

  return (
    <div className="page logs-page">
      <div className="logs-page__header">
        <div>
          <h1 className="page__title">Аудит</h1>
          <p className="page__lead logs-lead">
            Operational console · входы в админку, админ-действия, посещения, provider_switch · время: местное
          </p>
        </div>
        <OperationalRefreshButton
          loading={auditLoading}
          onClick={() => setRefreshNonce((n) => n + 1)}
        />
      </div>

      {auditError ? (
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
                  <option value="admin_action">админ-действия</option>
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
              </div>
              <div className="logs-page-controls">
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={() => setAuditPage((p) => Math.max(0, p - 1))}
                  disabled={auditPage <= 0 || auditLoading}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={() => setAuditPage((p) => Math.min(lastAuditPageIndex, p + 1))}
                  disabled={auditPage >= lastAuditPageIndex || auditLoading}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={() => setAuditPage(0)}
                  disabled={auditPage === 0}
                >
                  Сброс
                </button>
              </div>
            </div>

            <div className="logs-list">
              {auditLoading && auditLogs.length === 0 ? (
                <Loading />
              ) : auditLogs.length === 0 ? (
                <EmptyState message="За выбранный период audit-записи не найдены." />
              ) : (
                auditLogs.map((log) => {
                  const status = normalizeStatus(log.status);
                  const meta = log.metadata || {};
                  const preview =
                    log.event_type === "admin_action"
                      ? `${log.query ?? "—"}${meta.resource_id ? ` · ${meta.resource_id}` : ""}`
                      : log.event_type === "admin_login"
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
                        <span className="mono logs-item__ts">{formatTimestampLocal(log.created_at)}</span>
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
                      <dd className="mono">{formatTimestampLocal(selectedAuditLog.created_at)}</dd>
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