import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  listSources,
  createSource,
  buildAdmissionPreview,
  getLatestAdmissionPreview,
  updateDraftPatterns,
  resetDraftPatterns,
  approveSourceComposition,
  blockSource,
  unblockSource,
  listAdmissionEvents,
  type AdmissionEvent,
  type AdmissionPreview,
  type KnowledgeSource,
  type ApiError,
} from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Modal } from '../components/Modal';

const STATUS_FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'approved', label: 'Одобрен' },
  { key: 'need_preview', label: 'Нужен preview' },
  { key: 'preview_ready', label: 'Preview готов' },
  { key: 'patterns_changed', label: 'Есть изменения' },
  { key: 'blocked', label: 'Заблокирован' },
  { key: 'error', label: 'Ошибка' },
] as const;

const STATUS_LABELS: Record<string, string> = {
  approved: 'ОДОБРЕН',
  need_preview: 'НУЖЕН PREVIEW',
  preview_ready: 'PREVIEW ГОТОВ',
  patterns_changed: 'ЕСТЬ ИЗМЕНЕНИЯ',
  blocked: 'ЗАБЛОКИРОВАН',
  error: 'ОШИБКА',
};

const DRAFT_LABELS: Record<string, string> = {
  clean: 'БЕЗ ИЗМЕНЕНИЙ',
  dirty: 'ИЗМЕНЕНО',
  need_preview: 'НУЖЕН PREVIEW',
  preview_error: 'ОШИБКА В ПАТТЕРНЕ',
};

function emptyToText(patterns: string[] | null | undefined): string {
  return (patterns ?? []).join('\n');
}

function textToPatterns(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function samePatterns(a: string[] | null | undefined, b: string[] | null | undefined): boolean {
  const norm = (list: string[] | null | undefined) =>
    (list ?? []).map((p) => p.trim()).filter(Boolean).sort();
  return JSON.stringify(norm(a)) === JSON.stringify(norm(b));
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso.slice(0, 16);
  }
}

function parseGitHubUrl(url: string): string | null {
  const value = url.trim().replace(/\.git$/, '').replace(/\/+$/, '');
  if (!value) return null;
  const match = value.match(/(?:github\.com[/:])?([\w.-]+)\/([\w.-]+)/i);
  if (!match || match[1].toLowerCase() === 'github.com') return null;
  return `${match[1]}/${match[2]}`;
}

function eventIcon(type: string): string {
  switch (type) {
    case 'approved': return '✔';
    case 'blocked': return '⛔';
    case 'unblocked': return '🔓';
    case 'preview_created': return '☰';
    case 'preview_failed': return '⚠';
    case 'approval_rejected': return '⚠';
    case 'created': return '+';
    default: return '·';
  }
}

function sourceTitle(s: KnowledgeSource): string {
  return s.display_name?.trim() || s.identifier;
}

export function AdmissionConsolePage() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [actionNotice, setActionNotice] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null);

  const [preview, setPreview] = useState<AdmissionPreview | null>(null);
  const [events, setEvents] = useState<AdmissionEvent[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]['key']>('all');

  const [includeText, setIncludeText] = useState('');
  const [excludeText, setExcludeText] = useState('');
  const draftDirtyRef = useRef(false);
  const draftTimerRef = useRef<number | null>(null);

  const [confirmAction, setConfirmAction] = useState<'approve' | 'block' | 'unblock' | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showPreviewDetails, setShowPreviewDetails] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', url: '', branch: 'main' });
  const [addError, setAddError] = useState('');

  const selected = useMemo(
    () => sources.find((s) => s.id === selectedId) ?? null,
    [sources, selectedId],
  );

  const reloadSources = useCallback(async () => {
    const res = await listSources();
    setSources(res.items);
    return res.items;
  }, []);

  const loadSourceDetails = useCallback(async (id: string) => {
    setPreviewLoading(true);
    try {
      const [p, e] = await Promise.all([
        getLatestAdmissionPreview(id).catch((err: ApiError) => {
          if (err?.statusCode === 404) return null;
          throw err;
        }),
        listAdmissionEvents(id).catch(() => ({ items: [] as AdmissionEvent[] })),
      ]);
      setPreview(p);
      setEvents(e.items);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    reloadSources()
      .then((items) => {
        if (items.length > 0) setSelectedId(items[0].id);
      })
      .catch((err) => setPageError(err instanceof Error ? err.message : 'Не удалось загрузить источники'))
      .finally(() => setLoading(false));
  }, [reloadSources]);

  // Load details on selection change; seed drafts from the source.
  const loadedForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId) return;
    const s = sources.find((x) => x.id === selectedId) ?? null;
    if (loadedForRef.current !== selectedId) {
      loadedForRef.current = selectedId;
      draftDirtyRef.current = false;
      setIncludeText(s ? emptyToText(s.draft_include_patterns ?? s.include_patterns) : '');
      setExcludeText(s ? emptyToText(s.draft_exclude_patterns ?? s.exclude_patterns) : '');
      setPreview(null);
      loadSourceDetails(selectedId).catch((err) =>
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось загрузить данные источника' }),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, sources]);

  // Debounced draft persistence: draft is a persistent server-side state.
  useEffect(() => {
    if (!selectedId || !draftDirtyRef.current) return;
    if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current);
    draftTimerRef.current = window.setTimeout(() => {
      draftTimerRef.current = null;
      updateDraftPatterns(selectedId, {
        include_patterns: textToPatterns(includeText),
        exclude_patterns: textToPatterns(excludeText),
      }).catch(() => { /* surfaced on preview build / next action */ });
    }, 800);
    return () => {
      if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current);
    };
  }, [includeText, excludeText, selectedId]);

  const draftState: keyof typeof DRAFT_LABELS = useMemo(() => {
    if (!selected) return 'clean';
    if (preview?.status === 'error') return 'preview_error';
    const dirty =
      draftDirtyRef.current ||
      !samePatterns(selected.draft_include_patterns, selected.include_patterns) ||
      !samePatterns(selected.draft_exclude_patterns, selected.exclude_patterns);
    if (!dirty) {
      if (selected.admission_status === 'approved') return 'clean';
      return 'need_preview';
    }
    if (preview && samePatterns(preview.include_patterns, draftDirtyRef.current ? textToPatterns(includeText) : selected.draft_include_patterns ?? selected.include_patterns)
      && samePatterns(preview.exclude_patterns, draftDirtyRef.current ? textToPatterns(excludeText) : selected.draft_exclude_patterns ?? selected.exclude_patterns)) {
      return 'need_preview';
    }
    return 'dirty';
  }, [selected, preview, includeText, excludeText]);

  const approvalCheck = useMemo(() => {
    if (!selected) return { allowed: false, reason: 'Выберите источник' as string };
    if (selected.admission_status === 'blocked') return { allowed: false, reason: 'Источник заблокирован — сначала разблокируйте' };
    if (!preview) return { allowed: false, reason: 'Preview не построен — сначала сформируйте preview' };
    if (preview.status !== 'ready') return { allowed: false, reason: `Последний preview завершился ошибкой: ${preview.error_message ?? ''}` };
    if (!samePatterns(preview.include_patterns, draftDirtyRef.current ? textToPatterns(includeText) : selected.draft_include_patterns ?? selected.include_patterns)
      || !samePatterns(preview.exclude_patterns, draftDirtyRef.current ? textToPatterns(excludeText) : selected.draft_exclude_patterns ?? selected.exclude_patterns)) {
      return { allowed: false, reason: 'Паттерны изменились с момента построения preview — сформируйте preview заново' };
    }
    if (selected.admission_status === 'approved' && selected.approved_preview_id === preview.id) {
      return { allowed: false, reason: 'Этот состав уже одобрен' };
    }
    return { allowed: true, reason: '' };
  }, [selected, preview, includeText, excludeText]);

  const filteredSources = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sources.filter((s) => {
      if (statusFilter !== 'all' && s.display_status !== statusFilter) return false;
      if (!q) return true;
      return (sourceTitle(s) + ' ' + s.identifier).toLowerCase().includes(q);
    });
  }, [sources, search, statusFilter]);

  const handleSelect = (id: string) => {
    setPageError('');
    setActionNotice(null);
    setSelectedId(id);
  };

  const runDetailAction = async (fn: () => Promise<unknown>, okText: string) => {
    if (!selected) return;
    setDetailBusy(true);
    try {
      await fn();
      await reloadSources();
      await loadSourceDetails(selected.id);
      setActionNotice({ kind: 'ok', text: okText });
    } catch (err) {
      setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Операция не выполнена' });
    } finally {
      setDetailBusy(false);
    }
  };

  const handleBuildPreview = () => {
    if (!selected) return;
    setDetailBusy(true);
    setPageError('');
    (async () => {
      try {
        await updateDraftPatterns(selected.id, {
          include_patterns: textToPatterns(includeText),
          exclude_patterns: textToPatterns(excludeText),
        });
        const p = await buildAdmissionPreview(selected.id);
        setPreview(p);
        await reloadSources();
        await loadSourceDetails(selected.id);
        setActionNotice({ kind: 'ok', text: 'Preview построен' });
      } catch (err) {
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось построить preview' });
      } finally {
        setDetailBusy(false);
      }
    })();
  };

  const handleResetDraft = () => {
    if (!selected) return;
    setDetailBusy(true);
    (async () => {
      try {
        const s = await resetDraftPatterns(selected.id);
        draftDirtyRef.current = false;
        setIncludeText(emptyToText(s.include_patterns));
        setExcludeText(emptyToText(s.exclude_patterns));
        await reloadSources();
        setActionNotice({ kind: 'ok', text: 'Изменения правил отменены' });
      } catch (err) {
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось отменить изменения' });
      } finally {
        setDetailBusy(false);
      }
    })();
  };

  const handleConfirmAction = () => {
    if (!selected || !confirmAction) return;
    const action = confirmAction;
    setConfirmAction(null);
    if (action === 'approve') {
      runDetailAction(() => approveSourceComposition(selected.id), 'Состав одобрен: preview стал эффективными правилами (синхронизация не запускалась)');
    } else if (action === 'block') {
      runDetailAction(() => blockSource(selected.id), 'Источник заблокирован');
    } else {
      runDetailAction(() => unblockSource(selected.id), 'Источник разблокирован');
    }
  };

  const handleCreateSource = () => {
    setAddError('');
    const identifier = parseGitHubUrl(addForm.url);
    if (!identifier) {
      setAddError('Укажите корректный URL GitHub-репозитория (например, https://github.com/owner/repo)');
      return;
    }
    createSource({
      source_type: 'github_repo',
      identifier,
      display_name: addForm.name.trim() || identifier.split('/')[1],
      branch: addForm.branch.trim() || 'main',
      is_enabled: true,
      include_patterns: [],
      exclude_patterns: [],
    })
      .then(async (created) => {
        setShowAdd(false);
        setAddForm({ name: '', url: '', branch: 'main' });
        const items = await reloadSources();
        setSelectedId(created.id);
        loadedForRef.current = created.id;
        const s = items.find((x) => x.id === created.id);
        setIncludeText(emptyToText(s?.include_patterns ?? []));
        setExcludeText(emptyToText(s?.exclude_patterns ?? []));
      })
      .catch((err) => setAddError(err instanceof Error ? err.message : 'Не удалось создать источник'));
  };

  const dirtyNow = draftDirtyRef.current
    || (!!selected && (!samePatterns(selected.draft_include_patterns, selected.include_patterns) || !samePatterns(selected.draft_exclude_patterns, selected.exclude_patterns)));

  return (
    <div className="ac-page">
      <div className="ac-layout">
        {/* Left column: sources */}
        <aside className="ac-col ac-col--sources">
          <div className="ac-col__head">
            <h2 className="ac-col__title">ИСТОЧНИКИ</h2>
            <button
              className="admin-btn admin-btn--primary admin-btn--small"
              type="button"
              onClick={() => setShowAdd(true)}
            >
              + Добавить GitHub-репозиторий
            </button>
          </div>
          <input
            className="ac-search"
            type="search"
            placeholder="Поиск по названию или репозиторию…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="ac-filters">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                className={`ac-filter${statusFilter === f.key ? ' ac-filter--active' : ''}`}
                onClick={() => setStatusFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="ac-source-list">
            {loading && <div className="ac-hint">Загрузка…</div>}
            {pageError && <div className="ac-hint ac-hint--error">{pageError}</div>}
            {!loading && !pageError && filteredSources.length === 0 && (
              <div className="ac-hint">Источники не найдены</div>
            )}
            {filteredSources.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`ac-source-item${s.id === selectedId ? ' ac-source-item--selected' : ''}`}
                onClick={() => handleSelect(s.id)}
              >
                <div className="ac-source-item__meta">
                  <span className="ac-source-item__date">{formatDate(s.created_at)}</span>
                  <span className={`ac-badge ac-badge--${s.display_status ?? 'need_preview'}`}>
                    {STATUS_LABELS[s.display_status ?? 'need_preview']}
                  </span>
                </div>
                <div className="ac-source-item__title">{sourceTitle(s)}</div>
                <div className="ac-source-item__line3">
                  <span>{s.branch || 'main'}</span>
                  <span>· {s.preview?.status === 'ready' ? `${s.preview.included_count} в KB` : '— в KB'}</span>
                  <span>· {s.preview?.status === 'ready' ? `${s.preview.excluded_count} исключено` : '— исключено'}</span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Center column: source detail */}
        <section className="ac-col ac-col--detail">
          {!selected && !loading && (
            <div className="ac-hint">Выберите источник слева</div>
          )}
          {selected && (
            <>
              <div className="ac-section">
                <h2 className="ac-section__title">СВОДКА ИСТОЧНИКА</h2>
                <div className="ac-cards-row">
                  <div className="ac-card">
                    <div className="ac-card__label">Проект / репозиторий</div>
                    <div className="ac-card__value">{sourceTitle(selected)}</div>
                    <div className="ac-card__muted">{selected.identifier} · ветка {selected.branch || 'main'}</div>
                  </div>
                  <div className="ac-card">
                    <div className="ac-card__label">Состав (последний preview)</div>
                    <div className="ac-card__value">
                      {preview && preview.status === 'ready'
                        ? `${preview.included_count} в KB · ${preview.excluded_count} исключено`
                        : selected.preview?.status === 'ready'
                          ? `${selected.preview.included_count} в KB · ${selected.preview.excluded_count} исключено`
                          : 'Preview не построен'}
                    </div>
                    <div className="ac-card__muted">
                      commit: {preview?.commit_sha ? preview.commit_sha.slice(0, 7) : preview?.status === 'ready' && selected.preview ? '—' : '—'}
                      {' · '}от {formatDateTime(preview?.created_at ?? selected.preview?.created_at)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="ac-section">
                <div className="ac-section__head">
                  <h2 className="ac-section__title">ПРАВИЛА ОТБОРА</h2>
                  <span className={`ac-draft-state ac-draft-state--${draftState}`}>{DRAFT_LABELS[draftState]}</span>
                </div>
                <div className="ac-editors">
                  <label className="ac-editor">
                    <span>Include-паттерны (по одному на строку; пусто = ничего не индексировать)</span>
                    <textarea
                      className="ac-editor__textarea"
                      rows={6}
                      value={includeText}
                      onChange={(e) => { draftDirtyRef.current = true; setIncludeText(e.target.value); }}
                      spellCheck={false}
                    />
                  </label>
                  <label className="ac-editor">
                    <span>Exclude-паттерны (приоритетнее include)</span>
                    <textarea
                      className="ac-editor__textarea"
                      rows={6}
                      value={excludeText}
                      onChange={(e) => { draftDirtyRef.current = true; setExcludeText(e.target.value); }}
                      spellCheck={false}
                    />
                  </label>
                </div>
                <div className="ac-actions-row">
                  <button
                    className="admin-btn admin-btn--secondary"
                    type="button"
                    disabled={!selected || (!dirtyNow && selected.admission_status !== 'approved')}
                    onClick={handleResetDraft}
                    title="Вернуть черновик к текущим эффективным правилам"
                  >
                    Отменить изменения
                  </button>
                  <button
                    className="admin-btn admin-btn--primary"
                    type="button"
                    disabled={detailBusy}
                    onClick={handleBuildPreview}
                  >
                    Сформировать preview
                  </button>
                </div>
              </div>

              <div className="ac-section">
                <h2 className="ac-section__title">PREVIEW СОСТАВА</h2>
                {previewLoading && <div className="ac-hint">Загрузка preview…</div>}
                {!previewLoading && (!preview || preview.status !== 'ready') && (
                  <div className="ac-hint">
                    {preview?.status === 'error'
                      ? `Ошибка построения preview: ${preview.error_message ?? '—'}`
                      : 'Preview не построен. Измените правила и нажмите «Сформировать preview».'}
                  </div>
                )}
                {!previewLoading && preview?.status === 'ready' && (
                  <>
                    <div className="ac-preview-meta">
                      {preview.included_count} в KB · {preview.excluded_count} исключено · {preview.candidates_total} всего
                      {preview.stale ? ' · правила изменились после построения' : ''}
                    </div>
                    <div className="ac-preview-scroll">
                      <table className="admin-table ac-preview-table">
                        <thead>
                          <tr>
                            <th className="admin-table__header">Путь</th>
                            <th className="admin-table__header">Решение</th>
                            <th className="admin-table__header">Причина</th>
                            <th className="admin-table__header">Паттерн</th>
                          </tr>
                        </thead>
                        <tbody>
                          {preview.files.map((f) => (
                            <tr key={f.path}>
                              <td className="admin-table__cell ac-mono ac-nowrap" title={f.path}>{f.path}</td>
                              <td className="admin-table__cell">
                                <span className={`ac-decision ac-decision--${f.decision}`}>
                                  {f.decision === 'included' ? 'Include' : 'Exclude'}
                                </span>
                              </td>
                              <td className="admin-table__cell">{f.reason}</td>
                              <td className="admin-table__cell ac-mono">{f.pattern ?? '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <button
                      type="button"
                      className="ac-details-toggle"
                      onClick={() => setShowPreviewDetails((v) => !v)}
                    >
                      {showPreviewDetails ? 'Скрыть технические детали' : 'Технические детали'}
                    </button>
                    {showPreviewDetails && (
                      <div className="ac-details">
                        <div>preview_id: <span className="ac-mono">{preview.id}</span></div>
                        <div>commit_sha: <span className="ac-mono">{preview.commit_sha ?? '—'}</span></div>
                        <div>построен: {formatDateTime(preview.created_at)}</div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
          {actionNotice && (
            <div className={`ac-notice ac-notice--${actionNotice.kind}`}>{actionNotice.text}</div>
          )}
        </section>

        {/* Right column: decision + history */}
        <aside className="ac-col ac-col--decision">
          <div className="ac-section">
            <h2 className="ac-section__title">РЕШЕНИЕ ПО ИСТОЧНИКУ</h2>
            {!selected && <div className="ac-hint">Выберите источник</div>}
            {selected && (
              <>
                <div className="ac-decision-status">
                  <div className="ac-card">
                    <div className="ac-card__label">Текущий статус</div>
                    <div className="ac-card__value">
                      <span className={`ac-badge ac-badge--${selected.display_status ?? 'need_preview'}`}>
                        {STATUS_LABELS[selected.display_status ?? 'need_preview']}
                      </span>
                    </div>
                    <div className="ac-card__muted">
                      {selected.admission_status === 'approved' && selected.approved_at
                        ? `Одобрен ${formatDateTime(selected.approved_at)} · состав действует до нового одобрения`
                        : selected.admission_status === 'blocked'
                          ? 'Источник заблокирован: не индексируется'
                          : 'Ожидает одобрения состава'}
                    </div>
                  </div>
                </div>
                <div className="ac-actions-row ac-actions-row--stack">
                  <button
                    className="admin-btn admin-btn--primary"
                    type="button"
                    disabled={!approvalCheck.allowed || detailBusy}
                    title={approvalCheck.allowed ? '' : approvalCheck.reason}
                    onClick={() => setConfirmAction('approve')}
                  >
                    Одобрить состав
                  </button>
                  {!approvalCheck.allowed && approvalCheck.reason && (
                    <div className="ac-disabled-reason">{approvalCheck.reason}</div>
                  )}
                  {selected.admission_status === 'blocked' ? (
                    <button
                      className="admin-btn"
                      type="button"
                      disabled={detailBusy}
                      onClick={() => setConfirmAction('unblock')}
                    >
                      Разблокировать
                    </button>
                  ) : (
                    <button
                      className="admin-btn admin-btn--danger"
                      type="button"
                      disabled={detailBusy}
                      onClick={() => setConfirmAction('block')}
                    >
                      Заблокировать
                    </button>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="ac-section ac-section--history">
            <h2 className="ac-section__title">ИСТОРИЯ РЕШЕНИЙ</h2>
            {!selected && <div className="ac-hint">Выберите источник</div>}
            {selected && events.length === 0 && <div className="ac-hint">Событий пока нет</div>}
            <div className="ac-history">
              {events.map((ev) => (
                <div key={ev.id} className={`ac-history-item ac-history-item--${ev.event_type}`}>
                  <div className="ac-history-line1">
                    {formatDateTime(ev.created_at)}
                    <span className="ac-history-icon">{eventIcon(ev.event_type)}</span>
                  </div>
                  <div className="ac-history-line2">{typeLabel(ev.event_type)}</div>
                  <div className="ac-history-line3">{ev.summary}</div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {confirmAction && selected && (
        <ConfirmDialog
          title={
            confirmAction === 'approve' ? 'Одобрить состав источника?'
              : confirmAction === 'block' ? 'Заблокировать источник?'
                : 'Разблокировать источник?'
          }
          message={
            confirmAction === 'approve'
              ? 'Preview станет действующим составом источника. Синхронизация и переиндексация при этом не запускаются — состав KB обновится при следующей синхронизации.'
              : confirmAction === 'block'
                ? 'Источник перестанет индексироваться при синхронизации. Прежний одобренный состав будет восстановлен при разблокировке, если был.'
                : 'Источник вернётся к прежнему одобренному составу, если он был, иначе — в статус pending.'
          }
          confirmText={confirmAction === 'approve' ? 'Одобрить' : confirmAction === 'block' ? 'Заблокировать' : 'Разблокировать'}
          onConfirm={handleConfirmAction}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {showAdd && (
        <Modal title="Добавить GitHub-репозиторий" onClose={() => setShowAdd(false)}>
          <form
            className="admin-form"
            onSubmit={(e) => { e.preventDefault(); handleCreateSource(); }}
          >
            <label className="admin-form__field">
              <span>Название проекта</span>
              <input
                type="text"
                value={addForm.name}
                onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Например, Prompt Review"
              />
            </label>
            <label className="admin-form__field">
              <span>GitHub repository URL *</span>
              <input
                type="text"
                value={addForm.url}
                onChange={(e) => setAddForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://github.com/owner/repo"
                required
              />
            </label>
            <label className="admin-form__field">
              <span>Ветка</span>
              <input
                type="text"
                value={addForm.branch}
                onChange={(e) => setAddForm((f) => ({ ...f, branch: e.target.value }))}
                placeholder="main"
              />
            </label>
            {addError && <div className="ac-hint ac-hint--error">{addError}</div>}
            <div className="admin-form__actions">
              <button className="admin-btn admin-btn--secondary" type="button" onClick={() => setShowAdd(false)}>
                Отмена
              </button>
              <button className="admin-btn admin-btn--primary" type="submit">
                Добавить
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function typeLabel(type: string): string {
  switch (type) {
    case 'approved': return 'Одобрение';
    case 'blocked': return 'Блокировка';
    case 'unblocked': return 'Разблокировка';
    case 'preview_created': return 'Preview';
    case 'preview_failed': return 'Ошибка preview';
    case 'approval_rejected': return 'Отклонение одобрения';
    case 'created': return 'Создание источника';
    case 'draft_updated': return 'Черновик правил';
    case 'draft_reset': return 'Отмена черновика';
    default: return type;
  }
}