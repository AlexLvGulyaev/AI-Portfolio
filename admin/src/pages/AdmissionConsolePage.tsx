import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import {
  listSources,
  createSource,
  buildAdmissionPreview,
  getLatestAdmissionPreview,
  updateDraftPatterns,
  approveSourceComposition,
  listAdmissionEvents,
  listProjectCards,
  listOwnerRepos,
  getChromaStatus,
  retrievalApi,
  getSyncJob,
  getRunningSyncJob,
  syncKnowledgeBase,
  type AdmissionEvent,
  type AdmissionPreview,
  type ChromaStatus,
  type GitHubRepoOption,
  type KnowledgeSource,
  type ProjectCard,
  type RetrievalOverview,
  type SyncJob,
  type ApiError,
} from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Modal } from '../components/Modal';
import { OperationalRefreshButton } from '../components/OperationalRefreshButton';
import { FlagIcon } from '../components/FlagIcon';
import { sourceStatusChip, SOURCE_STATUS_CHIP } from '../utils/chipContract';
import {
  formatDateLocal,
  formatShortDateTimeLocal,
  formatTimestampLocal,
} from '../utils/operationalLabels';

const STATUS_FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'approved', label: 'Одобрен' },
  { key: 'need_preview', label: 'Нужен preview' },
  { key: 'preview_ready', label: 'Preview готов' },
  { key: 'patterns_changed', label: 'Есть изменения' },
  { key: 'error', label: 'Ошибка' },
] as const;

// Статус «заблокирован» выведен из консоли (решение владельца 29.08): третья
// ветка state machine дублирует пустой одобренный состав. Backend-механизм
// block/unblock остаётся спящим для совместимости; неизвестный статус
// показывается значком «Нужен preview» (fallback в chipContract).
// Статусы допуска — значки из chipContract (эмодзи-контракт, правило 7):
// слово заменяется значком, тултип «Статус: Значение».

const SYNC_FILTERS = [
  { key: 'all', label: 'Синхронизация: все', emoji: '' },
  { key: 'ok', label: 'Синхронизирован', emoji: '✅' },
  { key: 'error', label: 'Ошибка sync', emoji: '❌' },
  { key: 'never', label: 'Не синхронизирован', emoji: '⬜' },
] as const;

type SyncFilterKey = (typeof SYNC_FILTERS)[number]['key'];

// Стандарт пагинации APL: ровно 7 айтемов на страницу.
const PAGE_SIZE = 7;

// Кухонные каталоги APL: в консоли допуска вообще не отображаются.
// Список захардкожен на фронте; backend дополнительно гарантирует только .md.
const KITCHEN_PREFIXES = ['task_history/', 'attachments/'];

function isKitchenPath(path: string): boolean {
  if (KITCHEN_PREFIXES.some((p) => path.startsWith(p))) return true;
  return path.split('/').some((seg) => seg.startsWith('.'));
}

// Захардкоженные эмпирические правила: подсказка при наведении на файл.
// Подсказка никогда не перемещает файл автоматически — решение всегда за человеком.
interface FileHint {
  text: string;
  warm: boolean;
}

const HINT_TEXTS: Record<string, string> = {
  'PROJECT_STATE.md': 'Внутренняя кухня APL: паспорт состояния проекта, не для публичной витрины KB',
  'IMPLEMENTATION_PLAN.md': 'Внутренняя кухня APL: технический план реализации, не для публичной витрины KB',
  'README.md': 'Публичное описание проекта — обычно включают в KB',
  'DEPLOYMENT_GUIDE.md': 'Инструкция развёртывания — обычно публичная',
};

function fileHint(path: string): FileHint | null {
  if (isKitchenPath(path)) {
    return { text: 'Внутренняя кухня APL: в KB не включают', warm: true };
  }
  const name = path.split('/').pop() ?? path;
  if (name === 'PROJECT_STATE.md' || name === 'IMPLEMENTATION_PLAN.md') {
    return { text: HINT_TEXTS[name], warm: true };
  }
  if (path.startsWith('docs/') && !path.slice(5).includes('/')) {
    return { text: 'Проектная документация docs/ — обычно публичная', warm: false };
  }
  const hint = HINT_TEXTS[name];
  return hint ? { text: hint, warm: false } : null;
}

function formatDate(iso: string | null | undefined): string {
  return formatDateLocal(iso);
}

function formatShortDateTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const out = formatShortDateTimeLocal(iso);
  return out === '—' ? '' : out;
}

type SyncState = 'ok' | 'error' | 'never';

function syncStateOf(s: KnowledgeSource): SyncState {
  if (s.last_sync_status === 'error') return 'error';
  if (s.last_sync_status === 'success') return 'ok';
  return 'never';
}

function syncValue(s: KnowledgeSource): string {
  const state = syncStateOf(s);
  if (state === 'never') return 'н/д';
  return `${state === 'ok' ? 'ок' : 'ошибка'} ${formatShortDateTime(s.last_sync_at)}`;
}

function syncLabel(s: KnowledgeSource): string {
  return `sync: ${syncValue(s)}`;
}

function formatDateTime(iso: string | null | undefined): string {
  return formatTimestampLocal(iso);
}

function eventIcon(type: string): string {
  switch (type) {
    case 'approved': return '✔';
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
  const [syncFilter, setSyncFilter] = useState<SyncFilterKey>('all');
  const [pageState, setPageState] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [chromaStatus, setChromaStatus] = useState<ChromaStatus | null>(null);
  const [retrievalOverview, setRetrievalOverview] = useState<RetrievalOverview | null>(null);
  const activeBackendName = retrievalOverview?.effective_backend ?? 'chroma';
  const activeBackendHealth = retrievalOverview?.backends?.[activeBackendName] ?? null;
  // Хранилище активного бэкенда: у chroma — имя коллекции, у weaviate — класс
  // из health-detail ("class=XxxChunk; ready").
  const activeBackendStore = useMemo(() => {
    if (!retrievalOverview) return null;
    if (activeBackendName === 'chroma') return chromaStatus?.collection_name ?? null;
    const m = (retrievalOverview.backends?.[activeBackendName]?.detail ?? '')
      .match(/class=([^\s;]+)/);
    return m ? m[1] : null;
  }, [retrievalOverview, chromaStatus, activeBackendName]);
  const [syncRunning, setSyncRunning] = useState(false);
  // Живой прогресс синхронизации (owner request 29.08): бэкенд пишет
  // stats.progress по каждой обработанной единице; опрос каждые 3с.
  const [syncProgress, setSyncProgress] = useState<SyncJob['stats']['progress'] | null>(null);
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingIndexRef = useRef<number | null>(null);

  // Состав источника: два списка путей, управляются даблкликом.
  // Затравка — из immutable-снапшота preview в БД; сеть — только по кнопкам.
  const [includedPaths, setIncludedPaths] = useState<string[]>([]);
  const [excludedPaths, setExcludedPaths] = useState<string[]>([]);
  const previewIdRef = useRef<string | null>(null);
  const buildingRef = useRef<Set<string>>(new Set());
  const [buildingComposition, setBuildingComposition] = useState(false);
  const sourcesRef = useRef<KnowledgeSource[]>([]);

  // Рефлексия списка источников в ref — для посева состава из правил.
  useEffect(() => {
    sourcesRef.current = sources;
  }, [sources]);

  const [confirmAction, setConfirmAction] = useState<'save' | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  // Политика «KB только о проектах реестра» (решение владельца 29.08, модель «А»):
  // источник подключается только через выбор карточки реестра. «Название проекта»
  // как свободный ввод исчезло — заголовок источника = title выбранной карточки.
  const [addForm, setAddForm] = useState({ cardId: '', repo: '', branch: 'main' });
  const [projectCards, setProjectCards] = useState<ProjectCard[]>([]);
  const [addError, setAddError] = useState('');
  // Список репозиториев владельца реестра (KB_REPO_OWNER) для селектора:
  // свободный ввод URL исчез после namespace-гварда — селектор читает
  // список прямо из GitHub (решение владельца 29.08).
  const [ownerRepos, setOwnerRepos] = useState<GitHubRepoOption[]>([]);
  const [reposState, setReposState] = useState<'loading' | 'ready' | 'error'>('loading');

  const loadOwnerRepos = () => {
    setReposState('loading');
    listOwnerRepos()
      .then((res) => {
        setOwnerRepos(res.repos);
        setReposState('ready');
      })
      .catch(() => setReposState('error'));
  };

  useEffect(() => {
    if (!showAdd) return;
    listProjectCards()
      .then((res) => setProjectCards(res.items))
      .catch(() => setProjectCards([]));
    loadOwnerRepos();
  }, [showAdd]);

  // Селектор репозиториев симметричен селектору карточек: уже подключённые
  // источники в списке не показываются — работа с ними идёт через айтем списка.
  const freeOwnerRepos = useMemo(
    () => ownerRepos.filter((r) => !r.connected),
    [ownerRepos],
  );

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
      // Списки состава перезасеиваются только при смене снапшота:
      // несохранённые ручные переносы при том же preview не теряются.
      if ((p?.id ?? null) !== previewIdRef.current) {
        previewIdRef.current = p?.id ?? null;
        if (p && p.status === 'ready') {
          const visible = p.files.filter((f) => !isKitchenPath(f.path));
          setIncludedPaths(visible.filter((f) => f.decision === 'included').map((f) => f.path));
          setExcludedPaths(visible.filter((f) => f.decision !== 'included').map((f) => f.path));
        } else {
          // Легаси-источник без снапшота: состояние состава доступно сразу —
          // сеем «включено» из действующих правил источника (явные пути).
          const src = sourcesRef.current.find((x) => x.id === id) ?? null;
          setIncludedPaths(
            (src?.draft_include_patterns ?? src?.include_patterns ?? [])
              .filter((pat) => pat.endsWith('.md') && !isKitchenPath(pat)),
          );
          setExcludedPaths([]);
          // «Исключено» требует списка файлов репо: один раз собираем снапшот
          // фоном (read-only, KB не трогается) — дальше выбор источника снова
          // читает только БД.
          if (!p && !buildingRef.current.has(id)) {
            buildingRef.current.add(id);
            setBuildingComposition(true);
            try {
              await buildAdmissionPreview(id);
              if (loadedForRef.current === id) await loadSourceDetails(id);
            } catch {
              if (loadedForRef.current === id) {
                setActionNotice({
                  kind: 'error',
                  text: 'Не удалось собрать состав из GitHub — нажмите «Обновить состав» позже',
                });
              }
            } finally {
              buildingRef.current.delete(id);
              setBuildingComposition(false);
            }
          }
        }
      }
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

  // Load details on selection change; seed composition lists from the DB snapshot.
  const loadedForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedId) return;
    if (loadedForRef.current !== selectedId) {
      loadedForRef.current = selectedId;
      previewIdRef.current = null;
      setPreview(null);
      loadSourceDetails(selectedId).catch((err) =>
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось загрузить данные источника' }),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, sources]);

  const filteredSources = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sources.filter((s) => {
      if (statusFilter !== 'all' && s.display_status !== statusFilter) return false;
      if (syncFilter !== 'all' && syncStateOf(s) !== syncFilter) return false;
      if (!q) return true;
      return (sourceTitle(s) + ' ' + s.identifier).toLowerCase().includes(q);
    });
  }, [sources, search, statusFilter, syncFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredSources.length / PAGE_SIZE));
  const page = Math.min(pageState, totalPages - 1);
  const pageItems = useMemo(
    () => filteredSources.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filteredSources, page],
  );

  // After a page flip triggered by keyboard navigation, focus lands at the
  // remembered index of the new page (per AIC canonical behavior).
  useEffect(() => {
    if (pendingIndexRef.current == null) return;
    const idx = pendingIndexRef.current;
    pendingIndexRef.current = null;
    const target = pageItems[idx];
    if (target) setSelectedId(target.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageState, filteredSources]);

  // Keep DOM focus on the selected item: arrows and screen readers navigate
  // the list, and the browser scrolls the focused item into view.
  useEffect(() => {
    const el = listRef.current?.querySelector('.ac-source-item--selected') as HTMLElement | null;
    el?.focus({ preventScroll: true });
  }, [selectedId, pageState, filteredSources.length]);

  const handleListKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const idx = pageItems.findIndex((s) => s.id === selectedId);
    if (e.key === 'ArrowDown') {
      if (idx >= 0 && idx + 1 < pageItems.length) {
        handleSelect(pageItems[idx + 1].id);
      } else if (page + 1 < totalPages) {
        pendingIndexRef.current = 0;
        setPageState(page + 1);
      }
    } else if (idx > 0) {
      handleSelect(pageItems[idx - 1].id);
    } else if (page > 0) {
      pendingIndexRef.current = PAGE_SIZE - 1;
      setPageState(page - 1);
    }
  };

  const resetListControls = () => {
    setSearch('');
    setStatusFilter('all');
    setSyncFilter('all');
    setPageState(0);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await reloadSources();
      if (selectedId) await loadSourceDetails(selectedId).catch(() => { /* keep current details */ });
    } catch (err) {
      setPageError(err instanceof Error ? err.message : 'Не удалось обновить список');
    } finally {
      setRefreshing(false);
    }
  };

  const loadChromaStatus = useCallback(() => {
    // Стрип «Активный бэкенд» показывает effective-бэкенд Retrieval-менеджера
    // (индексация следует за активным бэкендом, решение владельца 29.08.2026),
    // а не только Chroma: счётчик чанков берём из матрицы здоровья активного.
    Promise.all([
      getChromaStatus(),
      retrievalApi.overview(),
    ])
      .then(([status, retrieval]) => {
        setChromaStatus(status);
        setRetrievalOverview(retrieval);
      })
      .catch(() => { /* стрип покажет последний известный статус / — */ });
  }, []);

  useEffect(() => {
    loadChromaStatus();
  }, [loadChromaStatus]);

  // Ручной запуск синхронизации KB (переехал из легаси-страницы «Синхронизация»):
  // POST sync → опрос job'а раз в 3с → итог в notice консоли.
  // Опрос синк-job'а до завершения; используется и сразу после запуска,
  // и при повторном заходе на страницу (re-attach к живому job'у).
  const watchJob = useCallback((jobId: string) => {
    if (syncPollRef.current) clearInterval(syncPollRef.current);
    setSyncRunning(true);
    syncPollRef.current = setInterval(() => {
      getSyncJob(jobId)
        .then((res) => {
          if (res.status === 'running') {
            setSyncProgress(res.stats.progress ?? null);
            return;
          }
          if (syncPollRef.current) clearInterval(syncPollRef.current);
          syncPollRef.current = null;
          setSyncRunning(false);
          setSyncProgress(null);
          loadChromaStatus();
          reloadSources();
          if (res.status === 'success') {
            setActionNotice({
              kind: 'ok',
              text: `Синхронизация завершена: источников ${res.stats.sources_processed} · документов ${res.stats.documents_processed} · чанков ${res.stats.chunks_created}${res.stats.errors.length ? ` · ошибок: ${res.stats.errors.length}` : ''}`,
            });
          } else {
            setActionNotice({ kind: 'error', text: `Синхронизация завершилась со статусом «${res.status}»${res.error_message ? `: ${res.error_message}` : ''}` });
          }
        })
        .catch(() => {
          if (syncPollRef.current) clearInterval(syncPollRef.current);
          syncPollRef.current = null;
          setSyncRunning(false);
          setSyncProgress(null);
          setActionNotice({ kind: 'error', text: 'Не удалось проверить статус синхронизации' });
        });
    }, 3000);
  }, [loadChromaStatus, reloadSources]);

  const handleSync = async () => {
    if (syncRunning) return;
    setSyncProgress({ stage: 'github', total: 0, done: 0, current: null });
    setActionNotice({ kind: 'ok', text: 'Синхронизация KB запущена…' });
    try {
      const job = await syncKnowledgeBase();
      watchJob(job.job_id);
    } catch (err) {
      setSyncProgress(null);
      setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Синхронизация не удалась' });
    }
  };

  // Re-attach (вариант «А»): перезагрузка страницы убивает таймер этого
  // компонента, но job продолжает бежать на сервере — при загрузке
  // переприсоединяемся к живому job'у и восстанавливаем прогрессбар.
  useEffect(() => {
    getRunningSyncJob()
      .then((job) => {
        if (job) {
          setSyncProgress(job.stats.progress ?? null);
          watchJob(job.job_id);
        }
      })
      .catch(() => { /* живого job'а нет — нормальный случай */ });
  }, [watchJob]);

  useEffect(() => () => { if (syncPollRef.current) clearInterval(syncPollRef.current); }, []);

  const handleSelect = (id: string) => {
    setPageError('');
    setActionNotice(null);
    setSelectedId(id);
  };

  // Списки изменились относительно снапшота preview → есть что сохранять.
  const compDirty = useMemo(() => {
    if (!preview || preview.status !== 'ready') return false;
    const snapIncluded = preview.files.filter((f) => f.decision === 'included' && !isKitchenPath(f.path)).map((f) => f.path);
    const snapExcluded = preview.files.filter((f) => f.decision !== 'included' && !isKitchenPath(f.path)).map((f) => f.path);
    const asSet = (xs: string[]) => new Set(xs);
    if (asSet(includedPaths).size !== asSet(snapIncluded).size) return true;
    if (asSet(excludedPaths).size !== asSet(snapExcluded).size) return true;
    for (const p of includedPaths) if (!snapIncluded.includes(p)) return true;
    for (const p of excludedPaths) if (!snapExcluded.includes(p)) return true;
    return false;
  }, [preview, includedPaths, excludedPaths]);

  // «Обновить состав»: draft ← текущие списки → новый preview с GitHub.
  // Новые .md-файлы приходят в «исключено» (include — явные пути).
  const handleRefreshComposition = async () => {
    if (!selected) return;
    setDetailBusy(true);
    (async () => {
      try {
        await updateDraftPatterns(selected.id, {
          include_patterns: includedPaths,
          exclude_patterns: excludedPaths,
        });
        const p = await buildAdmissionPreview(selected.id);
        setPreview(p);
        await reloadSources();
        await loadSourceDetails(selected.id);
        setActionNotice({
          kind: 'ok',
          text: p.status === 'ready'
            ? `Состав обновлён с GitHub: ${p.included_count} в KB · ${p.excluded_count} исключено · commit ${p.commit_sha?.slice(0, 7) ?? '—'}`
            : `Не удалось построить состав: ${p.error_message ?? '—'}`,
        });
      } catch (err) {
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось обновить состав' });
      } finally {
        setDetailBusy(false);
      }
    })();
  };

  // «Сохранить»: draft ← списки → preview → approve. Синхронизация не запускается.
  const handleSaveComposition = () => {
    if (!selected) return;
    setDetailBusy(true);
    (async () => {
      try {
        await updateDraftPatterns(selected.id, {
          include_patterns: includedPaths,
          exclude_patterns: excludedPaths,
        });
        const p = await buildAdmissionPreview(selected.id);
        await approveSourceComposition(selected.id);
        await reloadSources();
        await loadSourceDetails(selected.id);
        setActionNotice({
          kind: 'ok',
          text: p.status === 'ready'
            ? `Состав сохранён и одобрен: ${p.included_count} в KB · commit ${p.commit_sha?.slice(0, 7) ?? '—'} (синхронизация не запускалась)`
            : 'Состав сохранён, но preview завершился ошибкой',
        });
      } catch (err) {
        setActionNotice({ kind: 'error', text: err instanceof Error ? err.message : 'Не удалось сохранить состав' });
      } finally {
        setDetailBusy(false);
      }
    })();
  };

  const handleConfirmAction = () => {
    if (!selected || confirmAction !== 'save') return;
    setConfirmAction(null);
    handleSaveComposition();
  };

  // Политика + UX (решение 29.08): селектор предлагает только карточки, у которых
  // ещё нет ни одного источника (в любом статусе), и не-дочерние. Источник карточки
  // с уже подключённым проектом возобновляется через существующий айтем списка.
  const freeProjectCards = useMemo(
    () => projectCards.filter(
      (c) => !c.is_child_project && !sources.some((s) => s.project_card_id === c.id),
    ),
    [projectCards, sources],
  );

  const handleCreateSource = () => {
    setAddError('');
    const card = projectCards.find((c) => c.id === addForm.cardId);
    if (!card) {
      setAddError('Выберите проект из реестра — свободные источники запрещены');
      return;
    }
    const identifier = addForm.repo;
    if (!identifier) {
      setAddError('Выберите репозиторий из списка — репозитории вне namespace владельца реестра не допускаются');
      return;
    }
    createSource({
      source_type: 'github_repo',
      identifier,
      project_card_id: card.id,
      display_name: card.title,
      branch: addForm.branch.trim() || 'main',
      is_enabled: true,
      include_patterns: [],
      exclude_patterns: [],
    })
      .then(async (created) => {
        setShowAdd(false);
        setAddForm({ cardId: '', repo: '', branch: 'main' });
        await reloadSources();
        // ВАЖНО: loadedForRef здесь НЕ трогаем — смена selectedId запускает
        // штатный эффект загрузки (сброс preview/состава + загрузка деталей
        // + фоновая сборка первого снапшота). Ручная метка "loaded" глушит
        // этот эффект, и панели остаются с данными предыдущего источника.
        setSelectedId(created.id);
      })
      .catch((err) => setAddError(err instanceof Error ? err.message : 'Не удалось создать источник'));
  };

  const moveFile = (path: string) => {
    if (includedPaths.includes(path)) {
      setIncludedPaths(includedPaths.filter((p) => p !== path));
      setExcludedPaths([...excludedPaths, path]);
    } else {
      setExcludedPaths(excludedPaths.filter((p) => p !== path));
      setIncludedPaths([...includedPaths, path]);
    }
  };

  return (
    <div className="ac-page">
      <header className="ac-page__head">
        <div className="ac-head__id">
          <h1 className="page__title">Источники и синхронизация</h1>
          <p className="page__lead ac-page__lead">
            Admission Console · управление составом KB
          </p>
        </div>
      </header>
      {/* Тулбар-стрип по канону AIC «Документы»: актив бэкенда + саммари корпуса, правее кнопки.
          Сетка стрипа зеркалит .ac-layout: разделитель после статов корпуса — на правом крае
          левой макропанели, кнопки — от левого края средней панели, «Обновить» — правый край. */}
      <div className="ac-strip">
        <div className="ac-strip__info">
          <div className="ac-strip__backend">
            <div className="ac-strip__label">Активный бэкенд</div>
            <div className="ac-strip__value">
              <span className={`ac-strip__badge${activeBackendHealth?.ok ? '' : ' ac-strip__badge--err'}`}>
                {(retrievalOverview?.effective_backend ?? 'chroma').toUpperCase()}
              </span>
            </div>
          </div>
          <div className="ac-strip__stats">
            <div className="ac-strip__collection">{activeBackendStore ?? chromaStatus?.collection_name ?? '—'}</div>
            <div className="ac-strip__counts">
              {activeBackendHealth?.count ?? chromaStatus?.chunks ?? '—'} чанков · {chromaStatus?.documents ?? '—'} документов
            </div>
          </div>
        </div>
        <div className="ac-strip__actions">
          <button
            className="admin-btn admin-btn--small"
            type="button"
            onClick={() => setShowAdd(true)}
          >
            + Добавить GitHub-репозиторий
          </button>
          <button
            className="admin-btn admin-btn--primary admin-btn--small"
            type="button"
            onClick={handleSync}
            disabled={syncRunning}
            aria-busy={syncRunning || undefined}
          >
            {syncRunning ? 'Синхронизация…' : 'Синхронизировать KB'}
          </button>
        </div>
        <div className="ac-strip__refresh">
          <OperationalRefreshButton loading={refreshing || loading} onClick={handleRefresh} />
        </div>
      </div>
      {syncRunning && syncProgress && (
        <div className="ac-sync-progress" role="status">
          <div className="ac-sync-progress__text">
            Синхронизация KB · {syncProgress.done}/{syncProgress.total || '…'}
            {syncProgress.current && <span className="ac-sync-progress__current"> · {syncProgress.current}</span>}
          </div>
          <div className="ac-sync-progress__bar">
            <div
              className="ac-sync-progress__fill"
              style={syncProgress.total > 0
                ? { width: `${Math.min(100, Math.round((syncProgress.done / syncProgress.total) * 100))}%` }
                : { width: '8%', opacity: 0.45 }}
            />
          </div>
        </div>
      )}
      <div className="ac-layout">
        {/* Left column: sources */}
        <aside className="ac-col ac-col--sources">
          <div className="ac-filters-row">
            <select
              className="logs-select"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as typeof statusFilter); setPageState(0); }}
              aria-label="Фильтр по статусу допуска"
            >
              {/* Опции фильтра — значки того же семейства, что и флаги */}
              {STATUS_FILTERS.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.key === 'all' ? f.label : `${SOURCE_STATUS_CHIP[f.key as keyof typeof SOURCE_STATUS_CHIP].emoji} ${f.label}`}
                </option>
              ))}
            </select>
            <select
              className="logs-select"
              value={syncFilter}
              onChange={(e) => { setSyncFilter(e.target.value as SyncFilterKey); setPageState(0); }}
              aria-label="Фильтр по состоянию синхронизации"
            >
              {SYNC_FILTERS.map((f) => (
                <option key={f.key} value={f.key}>{f.emoji ? `${f.emoji} ${f.label}` : f.label}</option>
              ))}
            </select>
          </div>
          <input
            className="logs-search"
            type="search"
            placeholder="Поиск по названию или репозиторию…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPageState(0); }}
          />
          <div className="ac-pagination">
            <div className="ac-pagination__row">
              <button
                type="button"
                className="logs-page-btn"
                onClick={() => setPageState(page - 1)}
                disabled={page <= 0}
              >
                ← Назад
              </button>
              <span className="ac-pagination__counter">Страница {page + 1} из {totalPages}</span>
              <button
                type="button"
                className="logs-page-btn"
                onClick={() => setPageState(page + 1)}
                disabled={page >= totalPages - 1}
              >
                Вперёд →
              </button>
            </div>
            <div className="ac-pagination__row ac-pagination__row--meta">
              <span className="ac-pagination__total">Всего {filteredSources.length}</span>
              <button
                type="button"
                className="logs-page-btn logs-page-btn--muted"
                onClick={resetListControls}
                disabled={!search && statusFilter === 'all' && syncFilter === 'all' && pageState === 0}
              >
                Сброс
              </button>
            </div>
          </div>
          <div className="ac-source-list" ref={listRef} onKeyDown={handleListKeyDown}>
            {loading && <div className="ac-hint">Загрузка…</div>}
            {pageError && <div className="ac-hint ac-hint--error">{pageError}</div>}
            {!loading && !pageError && filteredSources.length === 0 && (
              <div className="ac-hint">Источники не найдены</div>
            )}
            {pageItems.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`ac-source-item${s.id === selectedId ? ' ac-source-item--selected' : ''}`}
                onClick={() => handleSelect(s.id)}
              >
                <div className="ac-source-item__line1">
                  <span className="ac-source-item__date">{formatDateTime(s.created_at)}</span>
                  {/* Флаг статуса — значок + тултип «Статус: Значение» */}
                  <FlagIcon chip={sourceStatusChip(s.display_status)} type="Статус" className="ac-source-item__status" />
                </div>
                <div className="ac-source-item__title">{sourceTitle(s)}</div>
                <div className="ac-source-item__params">
                  <span>{s.branch || 'main'}</span>
                  <span>· в KB: {s.preview?.status === 'ready' ? s.preview.included_count : 'н/д'}</span>
                  <span>· {syncLabel(s)}</span>
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
              {/* Заголовок макропанели целиком: на уровне колонки, не секции */}
              <h2 className="ac-summary-title">СВОДКА ИСТОЧНИКА</h2>
              <div className="ac-section ac-section--summary">
                <div className="ac-summary-grid">
                  <div className="op-panel">
                    <h3 className="op-panel__title">Паспорт</h3>
                    <div className="op-panel__body">
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Название</span>
                        <span className="op-meta-row__value">{sourceTitle(selected)}</span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Репозиторий</span>
                        <span className="op-meta-row__value ac-mono">{selected.identifier}</span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Ветка</span>
                        <span className="op-meta-row__value">{selected.branch || 'main'}</span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Тип</span>
                        <span className="op-meta-row__value">GitHub-репозиторий</span>
                      </div>
                    </div>
                  </div>
                  <div className="op-panel">
                    <h3 className="op-panel__title">Эксплуатация</h3>
                    <div className="op-panel__body">
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Добавлен</span>
                        <span className="op-meta-row__value">{formatDate(selected.created_at)}</span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Состав</span>
                        <span className="op-meta-row__value">
                          {(() => {
                            const p = preview ?? (selected.preview?.status === 'ready' ? selected.preview : null);
                            if (p && p.status === 'ready') {
                              return `в KB: ${p.included_count} · исключено: ${p.excluded_count}`;
                            }
                            const n = (selected.draft_include_patterns ?? selected.include_patterns ?? []).length;
                            return n > 0 ? `в KB: ${n} файлов (по действующим правилам)` : 'файлы одобрены будут составом ниже';
                          })()}
                        </span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Commit состава</span>
                        <span className="op-meta-row__value ac-mono">
                          {(() => {
                            const p = preview ?? (selected.preview?.status === 'ready' ? selected.preview : null);
                            return p?.commit_sha
                              ? `${p.commit_sha.slice(0, 7)} · от ${formatShortDateTime(p.created_at)}`
                              : '—';
                          })()}
                        </span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Одобрен</span>
                        <span className="op-meta-row__value">
                          {selected.approved_at ? formatDateTime(selected.approved_at) : 'ещё не одобрен'}
                        </span>
                      </div>
                      <div className="op-meta-row">
                        <span className="op-meta-row__label">Sync</span>
                        <span className="op-meta-row__value">{syncValue(selected)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="ac-section ac-comp">
                <div className="ac-comp-head">
                  <h2 className="ac-summary-title">СОСТАВ ИСТОЧНИКА ДЛЯ KB</h2>
                  <div className="ac-comp-head__actions">
                    <button
                      className="admin-btn admin-btn--secondary admin-btn--small"
                      type="button"
                      disabled={detailBusy}
                      title="Пересобрать состав с GitHub по текущим спискам; новые файлы попадут в «исключено»"
                      onClick={handleRefreshComposition}
                    >
                      Обновить состав
                    </button>
                    <button
                      className="admin-btn admin-btn--primary admin-btn--small"
                      type="button"
                      disabled={!preview || preview.status !== 'ready' || !compDirty || detailBusy}
                      title={compDirty ? '' : 'Изменений состава нет'}
                      onClick={() => setConfirmAction('save')}
                    >
                      Сохранить
                    </button>
                  </div>
                </div>
                {previewLoading && <div className="ac-hint">Загрузка состава…</div>}
                {!previewLoading && (!preview || preview.status !== 'ready') && (
                  <>
                    <div className="ac-zone">
                      <div className="ac-zone__label">ВКЛЮЧЕНО ({includedPaths.length})</div>
                      <div className="ac-zone__list">
                        {includedPaths.length === 0 && (
                          <div className="ac-zone__empty">Пусто — двойной клик на файле в «исключено», чтобы включить</div>
                        )}
                        {includedPaths.map((path) => (
                          <FileRow key={path} path={path} onMove={moveFile} />
                        ))}
                      </div>
                    </div>
                    <div className="ac-zone">
                      <div className="ac-zone__label">ИСКЛЮЧЕНО{preview && preview.status !== 'ready' && excludedPaths.length > 0 ? ` (${excludedPaths.length})` : ''}</div>
                      <div className="ac-zone__list">
                        {buildingComposition || previewLoading ? (
                          <div className="ac-zone__empty">Собираю список файлов с GitHub…</div>
                        ) : (
                          <div className="ac-zone__empty">
                            {preview?.status === 'error'
                              ? `Не удалось собрать состав: ${preview.error_message ?? '—'} — нажмите «Обновить состав»`
                              : 'Двойной клик на файле в «включено», чтобы исключить'}
                          </div>
                        )}
                        {excludedPaths.map((path) => (
                          <FileRow key={path} path={path} onMove={moveFile} />
                        ))}
                      </div>
                    </div>
                    <div className="ac-comp-foot">Двойной клик на файле перемещает его в соседний список · наведите курсор для подсказки</div>
                  </>
                )}
                {!previewLoading && preview?.status === 'ready' && (
                  <>
                    <div className="ac-zone">
                      <div className="ac-zone__label">ВКЛЮЧЕНО ({includedPaths.length})</div>
                      <div className="ac-zone__list">
                        {includedPaths.length === 0 && (
                          <div className="ac-zone__empty">Пусто — двойной клик на файле в «исключено», чтобы включить</div>
                        )}
                        {includedPaths.map((path) => (
                          <FileRow key={path} path={path} onMove={moveFile} />
                        ))}
                      </div>
                    </div>
                    <div className="ac-zone">
                      <div className="ac-zone__label">ИСКЛЮЧЕНО ({excludedPaths.length})</div>
                      <div className="ac-zone__list">
                        {excludedPaths.length === 0 && (
                          <div className="ac-zone__empty">Пусто — двойной клик на файле в «включено», чтобы исключить</div>
                        )}
                        {excludedPaths.map((path) => (
                          <FileRow key={path} path={path} onMove={moveFile} />
                        ))}
                      </div>
                    </div>
                    <div className="ac-comp-foot">
                      Двойной клик на файле перемещает его в соседний список · наведите курсор для подсказки
                      {preview.stale ? ' · правила изменились после построения' : ''}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
          {actionNotice && (
            <div className={`ac-notice ac-notice--${actionNotice.kind}`}>{actionNotice.text}</div>
          )}
        </section>

        {/* Right column: decision history only */}
        <aside className="ac-col ac-col--decision">
          {/* Заголовок макропанели целиком: на уровне колонки, не секции */}
          <h2 className="ac-summary-title">ИСТОРИЯ РЕШЕНИЙ</h2>
          <div className="ac-section ac-section--history">
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

      {confirmAction === 'save' && selected && (
        <ConfirmDialog
          title="Сохранить состав источника?"
          message="Списки «включено / исключено» станут одобренным составом источника в KB. Синхронизация и переиндексация при этом не запускаются — состав KB обновится при следующей синхронизации."
          confirmText="Сохранить"
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
              <span>Проект реестра *</span>
              <select
                value={addForm.cardId}
                onChange={(e) => setAddForm((f) => ({ ...f, cardId: e.target.value }))}
                required
              >
                <option value="">— выберите карточку из реестра —</option>
                {freeProjectCards.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}{c.is_visible ? '' : ' · скрыта'}
                  </option>
                ))}
              </select>
              {/* Политика KB (решение владельца 29.08): знания только о проектах
                  реестра; свободные и непривязанные источники запрещены; карточка
                  с уже подключённым источником в селектор не попадает. */}
              <span className="ac-hint">
                Источник подключается только к проекту реестра. Отображаемое имя = название карточки.
                Карточки, у которых источник уже подключён, в списке не показываются.
              </span>
            </label>
            <label className="admin-form__field">
              <span>GitHub-репозиторий *</span>
              <select
                value={addForm.repo}
                onChange={(e) => setAddForm((f) => ({ ...f, repo: e.target.value }))}
                disabled={reposState !== 'ready'}
                required
              >
                <option value="">
                  {reposState === 'loading' && '— загружаются репозитории владельца… —'}
                  {reposState === 'error' && '— GitHub недоступен, повторите попытку —'}
                  {reposState === 'ready' && `— выберите репозиторий владельца (${freeOwnerRepos.length}) —`}
                </option>
                {reposState === 'ready' && freeOwnerRepos.map((r) => (
                  <option key={r.identifier} value={r.identifier}>
                    {r.identifier}{r.archived ? ' · архив' : ''}
                  </option>
                ))}
              </select>
              {/* Список репозиториев берётся из namespace владельца реестра
                  (KB_REPO_OWNER) через GitHub API; уже подключённые источники
                  скрыты; namespace-гвард и live-проба на бэкенде остаются
                  последней линией. */}
              <span className="ac-hint">
                В списке — репозитории владельца реестра; уже подключённые не показываются.
                Существование репозитория проверяется при создании.
              </span>
              {reposState === 'error' && (
                <span>
                  <button type="button" className="admin-btn admin-btn--secondary" onClick={loadOwnerRepos}>
                    Повторить загрузку
                  </button>
                </span>
              )}
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

// Строка файла в зонах состава: hover-подсветка + подсказка, перемещение даблкликом.
// Подсказка только информирует — файлы автоматически не перемещает.
function FileRow({ path, onMove }: { path: string; onMove: (path: string) => void }) {
  const hint = fileHint(path);
  return (
    <div
      className={`ac-file${hint?.warm ? ' ac-file--warm' : ''}`}
      title={hint?.text ?? 'Двойной клик — переместить в соседний список'}
      onDoubleClick={() => onMove(path)}
    >
      {path}
    </div>
  );
}

function typeLabel(type: string): string {
  switch (type) {
    case 'approved': return 'Одобрение';
    case 'preview_created': return 'Preview';
    case 'preview_failed': return 'Ошибка preview';
    case 'approval_rejected': return 'Отклонение одобрения';
    case 'created': return 'Создание источника';
    case 'draft_updated': return 'Черновик правил';
    case 'draft_reset': return 'Отмена черновика';
    default: return type;
  }
}