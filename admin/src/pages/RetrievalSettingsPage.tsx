import { useCallback, useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { Loading } from '../components/Loading';
import { FlagIcon } from '../components/FlagIcon';
import { FLAG_CHIP, type FlagChipKey } from '../utils/chipContract';
import {
  RETRIEVAL_LABELS,
  retrievalApi,
  type RetrievalBackendHealth,
  type RetrievalCacheSection,
  type RetrievalOverview,
} from '../api/client';

/**
 * Логический экран настройки retrieval (recreated from Assistant Flow
 * RetrievalSettingsPage, task 2026-08-29): активный бэкенд, матрица
 * здоровья, runtime/build/indexing tuning, кеш поиска, пути.
 *
 * Визуальная стилистика приведена к канону «Системных настроек»
 * (DashboardPage): Page-обёртка, секции dashboard-section--compact с
 * uppercase-титулом и muted-сабтайтлом, бейджи admin-status, кнопки
 * admin-btn, токены --admin-* (task 2026-08-29, визуальная синхронизация).
 *
 * Layout-решения владельца 29.08.2026: панель кеша — справа от «Индексации»;
 * переопределения и пути — collapsed-панель внизу (AF retrieval-settings__details),
 * кнопка «Сбросить PG-переопределения» — внутри неё.
 */

type TuningGroup = 'runtime' | 'build' | 'indexing';

const GROUP_KEYS: Record<TuningGroup, string[]> = {
  runtime: [
    'rag_top_k',
    'rag_max_distance',
    'retrieval_recall_margin',
    'rag_answer_max_tokens',
    'rag_retrieval_timeout',
    'rag_embedding_request_timeout',
  ],
  build: ['chroma_ef_search', 'chroma_ef_construction'],
  indexing: ['rag_chunk_size', 'rag_chunk_overlap'],
};

const GROUP_TITLES: Record<TuningGroup, { title: string; description: string }> = {
  runtime: {
    title: 'Runtime-параметры (RAG-запрос)',
    description: 'Применяются на лету, ~2.5 c, без пересборки бэкенда.',
  },
  build: {
    title: 'Параметры создания коллекции Chroma (build-time)',
    description: 'Применяются при следующем создании коллекции (очистка/resync).',
  },
  indexing: {
    title: 'Индексация (чанкинг)',
    description: 'Изменение требует полной ресинхронизации базы знаний.',
  },
};

/* Готовность бэкенда — значок + тултип «Готовность: …»
   (эмодзи-контракт, правило 7). */
function readinessBadge(row: RetrievalBackendHealth | undefined): FlagChipKey {
  if (!row || !row.ok) return 'down';
  if (row.count == null) return 'flag_unknown';
  if (row.count === 0) return 'empty';
  return 'ready';
}

function SourceChip({ source }: { source?: string }) {
  return (
    <span
      className="rc-source"
      title={source === 'db' ? 'Переопределение в PostgreSQL' : 'Значение из env по умолчанию'}
    >
      {source === 'db' ? 'db' : 'env'}
    </span>
  );
}

export function RetrievalSettingsPage() {
  const [data, setData] = useState<RetrievalOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState('chroma');
  const [switching, setSwitching] = useState(false);
  const [lastWarnings, setLastWarnings] = useState<string[] | null>(null);

  const [draft, setDraft] = useState<Record<string, string>>({});
  const [tuningBusy, setTuningBusy] = useState(false);
  const [tuningError, setTuningError] = useState<string | null>(null);
  const [tuningNote, setTuningNote] = useState<string | null>(null);
  const [resyncFlag, setResyncFlag] = useState(false);

  const [cacheBusy, setCacheBusy] = useState(false);
  const [cacheError, setCacheError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ov = await retrievalApi.overview();
      setData(ov);
      setSelected(ov.effective_backend);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onApplySwitch = async () => {
    setSwitching(true);
    setLastWarnings(null);
    try {
      const res = await retrievalApi.switchBackend(selected);
      setLastWarnings(res.warnings);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSwitching(false);
    }
  };

  const onSaveAll = async () => {
    setTuningBusy(true);
    setTuningError(null);
    setTuningNote(null);
    setResyncFlag(false);
    try {
      // Одна кнопка на всю консоль: один PATCH из всех изменённых полей.
      const patch: Record<string, number> = {};
      for (const [k, v] of Object.entries(draft)) {
        if (v === undefined || v === '') continue;
        const num = Number(v);
        if (!Number.isFinite(num)) throw new Error(`${k}: не число`);
        patch[k] = num;
      }
      if (Object.keys(patch).length === 0) {
        setTuningError('Нет изменённых полей');
        return;
      }
      const res = await retrievalApi.saveTuning(patch);
      if (res.resync_required) setResyncFlag(true);
      setTuningNote(res.note ?? 'Сохранено');
      setDraft({});
      await load();
    } catch (e) {
      setTuningError(e instanceof Error ? e.message : String(e));
    } finally {
      setTuningBusy(false);
    }
  };

  const onClearOverrides = async () => {
    setTuningBusy(true);
    setTuningError(null);
    try {
      await retrievalApi.clearTuning();
      setDraft({});
      setTuningNote('Переопределения удалены — действуют env-значения');
      await load();
    } catch (e) {
      setTuningError(e instanceof Error ? e.message : String(e));
    } finally {
      setTuningBusy(false);
    }
  };

  const onCacheToggle = async (cache: RetrievalCacheSection) => {
    setCacheBusy(true);
    setCacheError(null);
    try {
      await retrievalApi.setCacheEnabled(!cache.enabled);
      await load();
    } catch (e) {
      setCacheError(e instanceof Error ? e.message : String(e));
    } finally {
      setCacheBusy(false);
    }
  };

  const onCacheClear = async () => {
    setCacheBusy(true);
    setCacheError(null);
    try {
      await retrievalApi.clearCache();
      await load();
    } catch (e) {
      setCacheError(e instanceof Error ? e.message : String(e));
    } finally {
      setCacheBusy(false);
    }
  };

  if (loading) return <Loading message="Загрузка retrieval-консоли..." />;
  if (error && !data) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!data) return <EmptyState message="Нет данных" />;

  const renderTuningGroup = (group: TuningGroup) => (
    <Card className="dashboard-section dashboard-section--compact">
      <h2 className="dashboard-section__title">{GROUP_TITLES[group].title}</h2>
      <p className="dashboard-section__subtitle">{GROUP_TITLES[group].description}</p>
      <div className="rc-grid">
        {GROUP_KEYS[group].map((k) => (
          <label key={k} className="rc-field">
            <span className="rc-field-label">
              <code>{k}</code>
              <span className="rc-field-title">{RETRIEVAL_LABELS[k]}</span>
              <SourceChip source={data.tuning.field_sources[k]} />
            </span>
            <input
              type="number"
              step="any"
              value={draft[k] ?? String(data.tuning.effective[k] ?? '')}
              onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      {group === 'indexing' && (
        <div className="rc-alert rc-alert--warn">
          Изменение размера чанка/перекрытия требует полной ресинхронизации базы знаний.
        </div>
      )}
      {group === 'build' && (
        <div className="rc-hint">
          Новый ef применяется только к новой коллекции: очистка/resync. Существующие данные не пересобираются.
        </div>
      )}
    </Card>
  );

  return (
    <Page
      title="Retrieval"
      subtitle="Векторные бэкенды, тюнинг RAG-параметров и пути корпуса"
      action={
        <>
          <button
            className="admin-btn admin-btn--small"
            type="button"
            disabled={tuningBusy || Object.keys(draft).length === 0}
            onClick={() => void onSaveAll()}
          >
            {tuningBusy ? 'Сохранение…' : 'Сохранить'}
          </button>
          <button className="admin-btn admin-btn--small admin-btn--secondary" type="button" disabled={loading} onClick={() => void load()}>
            Обновить
          </button>
        </>
      }
    >
      <div className="ret-stack">
        <div className="ret-cols">
          <Card className="dashboard-section dashboard-section--compact">
            <h2 className="dashboard-section__title">Активный бэкенд</h2>
            <p className="dashboard-section__subtitle">Effective-бэкенд, источник значений и переключение.</p>
            <div className="rc-kv-inline">
              <div><span>Effective</span><code>{data.effective_backend}</code></div>
              <div><span>Env дефолт</span><code>{data.env_default_backend}</code></div>
              <div>
                <span>DB active</span>
                {data.db_active_backend == null ? (
                  <em className="rc-muted">нет — действует env</em>
                ) : (
                  <code>{data.db_active_backend}</code>
                )}
              </div>
            </div>
            <div className="rc-switch-row">
              <label className="rc-switch-field">
                <span>Целевой бэкенд</span>
                <select value={selected} onChange={(e) => setSelected(e.target.value)} disabled={switching}>
                  {data.allowed_backends.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="admin-btn admin-btn--small"
                disabled={switching || selected === data.effective_backend}
                onClick={() => void onApplySwitch()}
              >
                {switching ? 'Переключение…' : 'Переключить'}
              </button>
            </div>
            <div className="rc-hint">
              KB-sync индексирует в эффективный бэкенд (сейчас: {data.effective_backend}).
              Неактивный бэкенд не обновляется — его readiness в матрице здоровья
              отражает последний свой sync.
            </div>
            {lastWarnings && lastWarnings.length > 0 && (
              <div className="rc-alert rc-alert--warn">
                {lastWarnings.map((w) => <div key={w}>{w}</div>)}
              </div>
            )}
            {data.warnings.length > 0 && (
              <div className="rc-alert rc-alert--err">
                {data.warnings.map((w) => <div key={w}>{w}</div>)}
              </div>
            )}
          </Card>

          <Card className="dashboard-section dashboard-section--compact">
            <h2 className="dashboard-section__title">Матрица здоровья бэкендов</h2>
            <p className="dashboard-section__subtitle">Readiness, объём индекса и активный бэкенд.</p>
            <table className="admin-table">
              <thead>
                <tr>
                  <th className="admin-table__header">Бэкенд</th>
                  <th className="admin-table__header">OK</th>
                  <th className="admin-table__header">Чанков</th>
                  <th className="admin-table__header">Готовность</th>
                  <th className="admin-table__header">Детали</th>
                </tr>
              </thead>
              <tbody>
                {data.allowed_backends.map((name) => {
                  const row = data.backends[name];
                  const rb = readinessBadge(row);
                  const active = name === data.effective_backend;
                  return (
                    <tr key={name} className={active ? 'rc-row-active' : undefined}>
                      <td className="admin-table__cell"><code>{name}</code>{active && <FlagIcon chip={FLAG_CHIP.active} type="Бэкенд" />}</td>
                      <td className="admin-table__cell">{row ? (row.ok ? '✔' : '✖') : '—'}</td>
                      <td className="admin-table__cell">{row?.count ?? '—'}</td>
                      <td className="admin-table__cell"><FlagIcon chip={FLAG_CHIP[rb]} type="Готовность" /></td>
                      <td className="admin-table__cell rc-detail">{row && !row.ok ? row.detail : row && row.count == null ? 'создайте коллекцию через resync' : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </div>

        <div className="ret-cols">
          {renderTuningGroup('runtime')}
          <Card className="dashboard-section dashboard-section--compact">
            <h2 className="dashboard-section__title">Retrieval cache</h2>
            <p className="dashboard-section__subtitle">Кеш результатов векторного поиска (WH-1, AF-parity).</p>
            <div
              className="rc-switch-row"
              title={`Ключ кеша: запрос + параметры вызова + runtime-тюнинг + embedding-модель + generation. По умолчанию выключен — включается здесь (env-дефолт ${data.cache.enabled_env_default ? 'ВКЛ' : 'ВЫКЛ'}).`}
            >
              <label className="rc-switch-field">
                <span>Кеш поиска</span>
                <select
                  value={data.cache.enabled ? 'on' : 'off'}
                  disabled={cacheBusy}
                  onChange={() => void onCacheToggle(data.cache)}
                >
                  <option value="off">выключен</option>
                  <option value="on">включен</option>
                </select>
              </label>
              <button
                type="button"
                className="admin-btn admin-btn--small"
                disabled={cacheBusy || data.cache.entry_count === 0}
                onClick={() => void onCacheClear()}
              >
                {cacheBusy ? '…' : 'Очистить кеш'}
              </button>
            </div>
            <div className="rc-kv rc-kv-cols">
              <div title="Время жизни записи кеша, сек (env RETRIEVAL_CACHE_TTL_SECONDS, read-only)">
                <span>TTL, с</span><code>{data.cache.ttl_seconds}</code>
              </div>
              <div title="Версия корпуса: растёт при успешном KB-sync, инвалидирует ключ кеша">
                <span>Generation</span><code>{data.cache.generation}</code>
              </div>
              <div title="Зарезервировано: роль играет отключённый ResponseCache (registry-only v4)">
                <span>ANSWER cache</span><code>reserved · off</code>
              </div>
              <div><span>Записей в кеше</span><code>{data.cache.entry_count}</code></div>
              <div title={data.cache.store_path}>
                <span>Хранилище</span><code>sqlite</code>
              </div>
              <div><span>Хиты</span><code>{data.cache.stats.hits}</code></div>
              <div><span>Промахи</span><code>{data.cache.stats.misses}</code></div>
              <div><span>Hit rate</span><code>{(data.cache.stats.hit_rate * 100).toFixed(1)}%</code></div>
              <div><span>Записано</span><code>{data.cache.stats.writes}</code></div>
              <div title="Записи с истёкшим TTL, удалённые при обращении">
                <span>Истекших</span><code>{data.cache.stats.evictions}</code>
              </div>
            </div>
            {cacheError && <span className="rc-alert rc-alert--err rc-inline">{cacheError}</span>}
          </Card>
        </div>

        <div className="ret-cols">
          {renderTuningGroup('indexing')}
          {renderTuningGroup('build')}
        </div>

        {(tuningError || tuningNote || resyncFlag) && (
          <div className="rc-actions">
            {tuningError && <span className="rc-alert rc-alert--err rc-inline">{tuningError}</span>}
            {resyncFlag && <span className="rc-alert rc-alert--warn rc-inline">Требуется resync базы знаний</span>}
            {tuningNote && <span className="rc-hint rc-inline">{tuningNote}</span>}
          </div>
        )}

        <details
          className="ret-details"
          onToggle={(e) => {
            // Раскрыли — выровнять НИЖНЮЮ границу панели по видимой области
            // (block:'nearest' не двигает уже видимый summary; содержимое
            // оставалось за нижним краем скролл-области).
            if ((e.target as HTMLDetailsElement).open) {
              e.currentTarget.scrollIntoView({ block: 'end' });
            }
          }}
        >
          <summary>Переопределения и пути</summary>
          <div className="ret-details__body">
            <div className="rc-hint">
              Переопределения хранятся в PostgreSQL (platform_settings.retrieval_tuning);
              env — источник первичных значений. Кнопка удаляет ВСЕ PG-переопределения.
            </div>
            <div className="rc-actions">
              <button
                type="button"
                className="admin-btn admin-btn--small admin-btn--secondary"
                disabled={tuningBusy || Object.keys(data.tuning.db_overrides).length === 0}
                onClick={() => void onClearOverrides()}
              >
                Сбросить PG-переопределения
              </button>
              {tuningError && <span className="rc-alert rc-alert--err rc-inline">{tuningError}</span>}
              {resyncFlag && <span className="rc-alert rc-alert--warn rc-inline">Требуется resync базы знаний</span>}
              {tuningNote && <span className="rc-hint rc-inline">{tuningNote}</span>}
            </div>
            {Object.keys(data.tuning.db_overrides).length > 0 && (
              <div className="rc-kv rc-kv-paths">
                {Object.entries(data.tuning.db_overrides).map(([k, v]) => (
                  <div key={k}><span><code>{k}</code></span><code>{String(v)}</code></div>
                ))}
              </div>
            )}
            <div className="rc-kv rc-kv-paths">
              {Object.entries(data.paths).map(([k, v]) => (
                <div key={k}><span>{k}</span><code>{String(v)}</code></div>
              ))}
            </div>
          </div>
        </details>
      </div>
    </Page>
  );
}