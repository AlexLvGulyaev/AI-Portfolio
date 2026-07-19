import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  getConversation,
  listConversations,
  type ChatSession,
  type ConversationDetail,
  type ConversationTurn,
} from '../api/client';
import { EmptyState } from '../components/EmptyState';
import { Loading } from '../components/Loading';
import { OperationalModalityBadge } from '../components/OperationalModalityBadge';
import { OperationalPipelineStageIcon } from '../components/OperationalPipelineStageIcon';
import { OperationalRefreshButton } from '../components/OperationalRefreshButton';
import { SessionJsonSnapshot } from '../components/SessionJsonSnapshot';
import {
  detailsJsonPreview,
  formatDetailsJson,
  operationalModalityFromRouteKey,
  pipelineStageVariant,
} from '../utils/operationalConsoleUi';
import {
  formatDurationMs,
  formatTimestampMsk,
  normalizeRouteKey,
  routeLabelRu,
  stageToActionRu,
  statusLabelRu,
} from '../utils/operationalLabels';

const LIST_FETCH_LIMIT = 200;
const PAGE_SIZE = 10;

const WINDOW_OPTIONS: Array<{ label: MemoryWindowLabel; ms: number }> = [
  { label: '24h', ms: 24 * 60 * 60 * 1000 },
  { label: '48h', ms: 48 * 60 * 60 * 1000 },
  { label: '7d', ms: 7 * 24 * 60 * 60 * 1000 },
];

type MemoryWindowLabel = '24h' | '48h' | '7d';
type ModeFilter = 'all' | 'rag' | 'text' | 'other';
type ActiveFilter = 'all' | 'active' | 'inactive';

function shortId(id: string | null | undefined, n = 8): string {
  if (!id) return '—';
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function toTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const n = new Date(iso).getTime();
  return Number.isFinite(n) ? n : null;
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

function pairDialogRows(turns: { role: string; content: string }[]): ConversationTurn[] {
  const rows: ConversationTurn[] = [];
  let pendingUser: string | null = null;
  for (const t of turns) {
    const r = (t.role || '').trim().toLowerCase();
    if (r === 'user') {
      if (pendingUser != null) {
        rows.push({ user: pendingUser, assistant: '—' });
      }
      pendingUser = t.content || '';
    } else if (r === 'assistant') {
      rows.push({ user: pendingUser || '—', assistant: t.content || '' });
      pendingUser = null;
    }
  }
  if (pendingUser != null) rows.push({ user: pendingUser, assistant: '—' });
  return rows;
}

function sessionListTimeMs(row: ChatSession): number | null {
  const raw = row.updated_at;
  if (!raw) return null;
  const ms = new Date(raw).getTime();
  return Number.isFinite(ms) ? ms : null;
}

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span className={`admin-status ${active ? 'admin-status--ok' : 'admin-status--muted'}`}>
      {active ? 'АКТИВНА' : 'НЕАКТИВНА'}
    </span>
  );
}

function ConversationDetailPanel({
  detail,
}: {
  detail: ConversationDetail;
}) {
  const dialogRows = useMemo(() => pairDialogRows(detail.messages), [detail.messages]);
  const latestExecution = detail.executions[0] ?? null;
  const runtime = detail.last_execution;
  const routeKey = runtime ? normalizeRouteKey(runtime.route) : normalizeRouteKey(detail.mode);
  const budget = detail.budget;

  return (
    <div className="logs-detail memory-detail-panel">
      <div className="logs-detail__head">
        <div>
          <h2 className="logs-detail__title">Сводка диалога</h2>
          <p className="logs-detail__sub muted">{shortId(detail.id, 12)}</p>
        </div>
        <ActiveBadge active={detail.is_active} />
      </div>

      <div className="logs-detail__route-line">
        {routeLabelRu(routeKey).toUpperCase()} · {detail.is_active ? 'АКТИВНА' : 'НЕАКТИВНА'}
      </div>

      <div className="logs-summary-grid">
        <div className="logs-summary-col">
          <dl className="kv logs-detail-kv">
            <OpsRow
              label="session_id"
              value={<span className="mono break-all">{detail.id}</span>}
            />
            <OpsRow
              label="visitor_id"
              value={<span className="mono break-all">{detail.visitor_id || '—'}</span>}
            />
            <OpsRow label="Режим" value={<span className="mono">{detail.mode || '—'}</span>} />
            <OpsRow label="Активна" value={<ActiveBadge active={detail.is_active} />} />
            <OpsRow label="Сообщений" value={String(detail.message_count)} />
            <OpsRow label="Turns~" value={String(detail.turns_approx)} />
            <OpsRow
              label="Обновлена"
              value={
                detail.updated_at ? (
                  <span className="mono">{formatTimestampMsk(detail.updated_at)}</span>
                ) : (
                  '—'
                )
              }
            />
          </dl>
        </div>
        <div className="logs-summary-col">
          <dl className="kv logs-detail-kv">
            <OpsRow label="RAG" value={runtime?.rag_used ? 'да' : 'нет'} />
            <OpsRow
              label="cache hit"
              value={runtime?.cache_hit === null ? '—' : runtime?.cache_hit ? 'да' : 'нет'}
            />
            <OpsRow
              label="provider / model"
              value={
                <span className="mono">
                  {runtime?.provider_key || '—'} / {runtime?.model_name || '—'}
                </span>
              }
            />
            <OpsRow
              label="response time"
              value={formatDurationMs(runtime?.response_time_ms)}
            />
            <OpsRow label="source" value={<span className="mono">{detail.memory_source}</span>} />
          </dl>
        </div>
        <div className="logs-summary-col">
          <dl className="kv logs-detail-kv">
            <OpsRow
              label="max_recent_messages"
              value={String(budget?.max_recent_messages ?? '—')}
            />
            <OpsRow
              label="max_message_chars"
              value={String(budget?.max_message_chars ?? '—')}
            />
            <OpsRow
              label="total_memory_chars_budget"
              value={String(budget?.total_memory_chars_budget ?? '—')}
            />
          </dl>
        </div>
      </div>

      <div className="memory-dialog-panel page__mt-sm">
        <h3 className="logs-detail-block__title">Диалог сессии</h3>
        <p className="muted memory-dialog-panel__lead">
          Парные реплики по времени; при неполном turn пустая ячейка.
        </p>
        <div className="memory-dialog-table-wrap">
          <table className="memory-dialog-table">
            <thead>
              <tr>
                <th>Что спросил пользователь</th>
                <th>Что ответила система</th>
              </tr>
            </thead>
            <tbody>
              {dialogRows.length ? (
                dialogRows.map((row, i) => (
                  <tr key={i}>
                    <td className="memory-dialog-table__cell memory-dialog-table__cell--user">
                      {row.user}
                    </td>
                    <td className="memory-dialog-table__cell memory-dialog-table__cell--assistant">
                      {row.assistant}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={2} className="muted memory-dialog-table__empty">
                    Нет user/assistant сообщений.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {latestExecution ? (
        <>
          <h3 className="logs-timeline-heading page__mt">
            Таймлайн execution pipeline
            {latestExecution.is_backfilled ? (
              <span
                className="logs-timeline-hint"
                title="Сессия создана автоматически из архивных operational logs. Длительности и интервалы между этапами приблизительные."
              >
                приблизительный
              </span>
            ) : null}
          </h3>
          <div className="logs-timeline">
            {latestExecution.steps.map((step, i) => {
              const prev = i > 0 ? toTs(latestExecution.steps[i - 1].created_at) : null;
              const cur = toTs(step.created_at);
              const delta = prev != null && cur != null ? Math.max(0, cur - prev) : null;
              const stageRaw = String(step.stage_name ?? '').trim();
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
        </>
      ) : null}

      <SessionJsonSnapshot
        className="page__mt"
        body={JSON.stringify(detail, null, 2)}
        summaryLabel="Технический снимок диалога (JSON)"
      />
    </div>
  );
}

export function ConversationsPage() {
  const [list, setList] = useState<{ items: ChatSession[]; total: number; limit: number; offset: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [windowLabel, setWindowLabel] = useState<MemoryWindowLabel>('24h');
  const [modeFilter, setModeFilter] = useState<ModeFilter>('all');
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [pageIndex, setPageIndex] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);

  const load = useMemo(
    () => async () => {
      setLoading(true);
      setError(null);
      try {
        const params: Parameters<typeof listConversations>[0] = {
          active_only: activeFilter === 'active' ? true : activeFilter === 'inactive' ? false : undefined,
          route: modeFilter === 'all' ? undefined : modeFilter,
          search: searchQuery.trim() || undefined,
          limit: LIST_FETCH_LIMIT,
          offset: 0,
        };
        const l = await listConversations(params);
        setList(l);
      } catch (e) {
        setList(null);
        setError(e instanceof Error ? e.message : 'Ошибка загрузки диалогов');
      } finally {
        setLoading(false);
      }
    },
    [activeFilter, modeFilter, searchQuery, refreshNonce]
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPageIndex(0);
  }, [searchQuery, activeFilter, modeFilter, windowLabel, refreshNonce]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    void getConversation(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setDetailError(e instanceof Error ? e.message : 'detail error');
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshNonce]);

  const filtered = useMemo(() => {
    const items = list?.items ?? [];
    const windowMs = WINDOW_OPTIONS.find((w) => w.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms;
    const cutoff = Date.now() - windowMs;
    return items.filter((r) => {
      const t = sessionListTimeMs(r);
      if (t == null) return false;
      return t >= cutoff;
    });
  }, [list, windowLabel]);

  const totalFiltered = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));
  const safePageIdx = useMemo(
    () => Math.min(pageIndex, Math.max(0, totalPages - 1)),
    [pageIndex, totalPages]
  );

  useEffect(() => {
    if (pageIndex !== safePageIdx) setPageIndex(safePageIdx);
  }, [pageIndex, safePageIdx]);

  const pageSessions = useMemo(() => {
    const start = safePageIdx * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, safePageIdx]);

  useEffect(() => {
    if (loading || error) return;
    if (totalFiltered === 0) {
      if (selectedId) setSelectedId(null);
      return;
    }
    const inFiltered = selectedId ? filtered.some((r) => r.id === selectedId) : false;
    const onCurrentPage = selectedId ? pageSessions.some((r) => r.id === selectedId) : false;

    if (!selectedId || !inFiltered) {
      setSelectedId(pageSessions[0]?.id ?? filtered[0]?.id ?? null);
      return;
    }
    if (!onCurrentPage) {
      setSelectedId(pageSessions[0]?.id ?? null);
    }
  }, [loading, error, totalFiltered, filtered, pageSessions, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const listEl = listRef.current;
    if (!listEl) return;
    const safeId =
      typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
        ? CSS.escape(selectedId)
        : selectedId.replace(/"/g, '\\"');
    const row = listEl.querySelector<HTMLButtonElement>(`[data-conversation-id="${safeId}"]`);
    if (!row) return;
    row.scrollIntoView({ block: 'nearest' });
    const listHasFocus =
      document.activeElement instanceof Node && listEl.contains(document.activeElement);
    const shouldFocus = pendingListFocusRef.current || listHasFocus;
    pendingListFocusRef.current = false;
    if (!shouldFocus) return;
    const id = window.requestAnimationFrame(() => {
      row.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [selectedId, safePageIdx]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.closest('input') || t.closest('textarea') || t.closest('select') || t.isContentEditable)
      ) {
        return;
      }
      if (!filtered.length) return;
      const curIdx = selectedId ? filtered.findIndex((s) => s.id === selectedId) : 0;
      if (curIdx < 0) return;
      const nextIdx =
        e.key === 'ArrowDown'
          ? Math.min(filtered.length - 1, curIdx + 1)
          : Math.max(0, curIdx - 1);
      if (nextIdx === curIdx) return;
      e.preventDefault();
      const next = filtered[nextIdx];
      if (!next?.id) return;
      pendingListFocusRef.current = true;
      setPageIndex(Math.floor(nextIdx / PAGE_SIZE));
      setSelectedId(next.id);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [filtered, selectedId, safePageIdx]);

  const goPrevPage = () => {
    pendingListFocusRef.current = true;
    const np = Math.max(0, safePageIdx - 1);
    setPageIndex(np);
    const pick = filtered[np * PAGE_SIZE]?.id ?? null;
    if (pick) setSelectedId(pick);
  };

  const goNextPage = () => {
    pendingListFocusRef.current = true;
    const np = Math.min(totalPages - 1, safePageIdx + 1);
    setPageIndex(np);
    const pick = filtered[np * PAGE_SIZE]?.id ?? null;
    if (pick) setSelectedId(pick);
  };

  const resetPagination = () => {
    setPageIndex(0);
    setSearchQuery('');
    setActiveFilter('all');
    setModeFilter('all');
    setWindowLabel('24h');
  };

  const listMetaLine = useMemo(() => {
    const p = safePageIdx + 1;
    const shown = pageSessions.length;
    return `Страница ${p} из ${totalPages} · сессий: ${totalFiltered} · показано: ${shown}`;
  }, [safePageIdx, totalPages, totalFiltered, pageSessions.length]);

  if (loading && !list) {
    return (
      <div className="page logs-page memory-console-page">
        <h1 className="page__title">Диалоги</h1>
        <p className="page__lead muted">Операционная консоль диалоговых сессий</p>
        <Loading />
      </div>
    );
  }

  const listEmpty = !loading && totalFiltered === 0;
  const rawEmpty = !(list?.items?.length ?? 0);

  return (
    <div className="page logs-page memory-console-page">
      <h1 className="page__title">Диалоги</h1>
      <p className="page__lead muted">Операционная консоль диалоговых сессий</p>

      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : (
        <div className="logs-console memory-logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row">
                <select
                  className="logs-select"
                  value={windowLabel}
                  onChange={(e) => setWindowLabel(e.target.value as MemoryWindowLabel)}
                  aria-label="Окно времени (по updated_at сессии)"
                >
                  {WINDOW_OPTIONS.map((w) => (
                    <option key={w.label} value={w.label}>
                      {w.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={modeFilter}
                  onChange={(e) => setModeFilter(e.target.value as ModeFilter)}
                  aria-label="Режим сессии"
                >
                  <option value="all">все режимы</option>
                  <option value="rag">RAG</option>
                  <option value="text">текст</option>
                  <option value="other">прочие</option>
                </select>
                <select
                  className="logs-select"
                  value={activeFilter}
                  onChange={(e) => setActiveFilter(e.target.value as ActiveFilter)}
                  aria-label="Статус активности"
                >
                  <option value="all">все статусы</option>
                  <option value="active">активные</option>
                  <option value="inactive">неактивные</option>
                </select>
              </div>
              <input
                className="logs-search memory-logs-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск: session_id, visitor_id, mode…"
                aria-label="Поиск сессий"
              />
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>{listMetaLine}</span>
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
                  disabled={safePageIdx <= 0 || totalFiltered === 0}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goNextPage}
                  disabled={safePageIdx >= totalPages - 1 || totalFiltered === 0}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={resetPagination}
                  disabled={
                    safePageIdx === 0 &&
                    !searchQuery.trim() &&
                    activeFilter === 'all' &&
                    modeFilter === 'all' &&
                    windowLabel === '24h'
                  }
                >
                  Сброс
                </button>
              </div>
            </div>
            <div className="logs-list" ref={listRef}>
              {loading && !list?.items?.length ? (
                <Loading />
              ) : listEmpty ? (
                <EmptyState
                  message={
                    rawEmpty
                      ? 'При пустой БД список пуст.'
                      : 'Измените поиск или снимите фильтры.'
                  }
                />
              ) : (
                pageSessions.map((row: ChatSession) => {
                  const sid = row.id;
                  const routeKey = normalizeRouteKey(row.last_execution?.route || row.mode);
                  return (
                    <button
                      key={sid}
                      type="button"
                      data-conversation-id={sid}
                      className={`logs-item memory-logs-item ${selectedId === sid ? 'logs-item--selected' : ''}`}
                      onClick={() => {
                        pendingListFocusRef.current = true;
                        setSelectedId(sid);
                      }}
                    >
                      <div className="logs-item__row logs-item__row--tight">
                        <span className="mono logs-item__ts">
                          {row.updated_at
                            ? formatTimestampMsk(row.updated_at)
                            : '—'}
                        </span>
                        <OperationalModalityBadge modality={operationalModalityFromRouteKey(routeKey)} />
                        <ActiveBadge active={row.is_active} />
                      </div>
                      <div className="logs-item__preview memory-logs-item__user" title={row.visitor_id || ''}>
                        {row.visitor_id ? `visitor: ${shortId(row.visitor_id, 12)}` : 'visitor: н/д'}
                      </div>
                      <div className="logs-item__row logs-item__meta muted">
                        <span className="mono truncate" title={sid}>
                          {shortId(sid, 12)}
                        </span>
                        <span>{row.mode}</span>
                        <span>msg {row.message_count ?? 0}</span>
                        <span>turns~ {row.turns_approx ?? 0}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="logs-right card">
            {listEmpty ? (
              <EmptyState
                message={
                  rawEmpty
                    ? 'Нет диалогов для просмотра.'
                    : 'Выберите другой фильтр.'
                }
              />
            ) : detailLoading && !detail ? (
              <Loading />
            ) : detailError ? (
              <div className="panel panel--error" role="alert">
                {detailError}
              </div>
            ) : detail && selectedId ? (
              <ConversationDetailPanel detail={detail} />
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
