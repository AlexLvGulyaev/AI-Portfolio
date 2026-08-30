import { useEffect, useMemo, useState } from 'react';
import { Page } from '../components/Page';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { Modal } from '../components/Modal';
import { OperationalRefreshButton } from '../components/OperationalRefreshButton';
import { formatTimestampLocal } from '../utils/operationalLabels';
import {
  listDocuments,
  listSources,
  getDocument,
  getDocumentText,
  getDocumentChunks,
  getChromaStatus,
  retrievalApi,
  type DocumentListItem,
  type DocumentCard,
  type DocumentText,
  type DocumentChunk,
  type DocumentsBackendInfo,
  type KnowledgeSource,
  type ChromaStatus,
  type RetrievalOverview,
} from '../api/client';

const PAGE_SIZE = 7;

function formatDateTime(value: string | null | undefined): string {
  return formatTimestampLocal(value);
}

function IndexStatusBadge({ chunkCount }: { chunkCount: number | null }) {
  if (chunkCount == null) {
    return <span className="admin-status admin-status--unknown">—</span>;
  }
  return chunkCount > 0
    ? <span className="admin-status admin-status--ok">В индексе</span>
    : <span className="admin-status admin-status--muted">Не в индексе</span>;
}

/* Тулбар-стрип канона AIC «Документы» (как в «Источниках и синхронизация»):
   одна панель во всю рабочую область — активный бэкенд + корпусная статистика. */
function BackendStrip({
  backendInfo,
  storeName,
  totalDocuments,
}: {
  backendInfo: DocumentsBackendInfo | null;
  storeName: string | null;
  totalDocuments: number | null;
}) {
  return (
    <div className="ac-strip">
      <div className="ac-strip__info">
        <div className="ac-strip__backend">
          <div className="ac-strip__label">Активный бэкенд</div>
          <div className="ac-strip__value">
            <span className={`ac-strip__badge${backendInfo?.state === 'ok' ? '' : ' ac-strip__badge--err'}`}>
              {(backendInfo?.backend ?? '—').toUpperCase()}
            </span>
          </div>
        </div>
        <div className="ac-strip__stats">
          <div className="ac-strip__collection">{storeName ?? '—'}</div>
          <div className="ac-strip__counts">
            {backendInfo?.chunks != null ? `${backendInfo.chunks} чанков` : '—'} · {totalDocuments ?? '—'} документов
          </div>
        </div>
      </div>
    </div>
  );
}

export function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentListItem[]>([]);
  const [totalDocuments, setTotalDocuments] = useState<number | null>(null);
  const [backendInfo, setBackendInfo] = useState<DocumentsBackendInfo | null>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [chromaStatus, setChromaStatus] = useState<ChromaStatus | null>(null);
  const [retrievalOverview, setRetrievalOverview] = useState<RetrievalOverview | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Фильтры левой макропанели (решение владельца 30.08.2026): источник + формат файла
  const [sourceId, setSourceId] = useState('');
  const [docFormat, setDocFormat] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [card, setCard] = useState<DocumentCard | null>(null);
  const [cardLoading, setCardLoading] = useState(false);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [fullText, setFullText] = useState<DocumentText | null>(null);
  const [textLoading, setTextLoading] = useState(false);

  // Хранилище активного бэкенда: chroma — имя коллекции, weaviate — класс из health-detail
  const activeBackendName = backendInfo?.backend ?? retrievalOverview?.effective_backend ?? 'chroma';
  const storeName = useMemo(() => {
    if (activeBackendName === 'chroma') return chromaStatus?.collection_name ?? null;
    const m = (retrievalOverview?.backends?.[activeBackendName]?.detail ?? '').match(/class=([^\s;]+)/);
    return m ? m[1] : null;
  }, [retrievalOverview, chromaStatus, activeBackendName]);

  const load = () => {
    setLoading(true);
    setError('');
    const params: { source_id?: string; search?: string } = {};
    if (sourceId) params.source_id = sourceId;
    if (search) params.search = search;
    listDocuments(Object.keys(params).length ? params : undefined)
      .then((data) => {
        setDocs(data.items);
        setTotalDocuments(data.total_documents);
        setBackendInfo(data.backend);
        setSelectedId((prev) => {
          if (prev && data.items.some((d) => d.id === prev)) return prev;
          return data.items[0]?.id ?? null;
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Unknown error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [sourceId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    listSources().then((d) => setSources(d.items)).catch(() => setSources([]));
    getChromaStatus().then(setChromaStatus).catch(() => setChromaStatus(null));
    retrievalApi.overview().then(setRetrievalOverview).catch(() => setRetrievalOverview(null));
  }, []);

  useEffect(() => {
    if (!selectedId) { setCard(null); setChunks([]); return; }
    setCardLoading(true);
    setChunksLoading(true);
    setCard(null);
    setChunks([]);
    getDocument(selectedId)
      .then(setCard)
      .catch((err) => setError(err instanceof Error ? err.message : 'Unknown error'))
      .finally(() => setCardLoading(false));
    getDocumentChunks(selectedId)
      .then((data) => setChunks(data.items))
      .catch(() => setChunks([]))
      .finally(() => setChunksLoading(false));
  }, [selectedId]);

  const openText = () => {
    if (!selectedId) return;
    setTextLoading(true);
    getDocumentText(selectedId)
      .then(setFullText)
      .catch((err) => setError(err instanceof Error ? err.message : 'Unknown error'))
      .finally(() => setTextLoading(false));
  };

  // Формат файла — из расширения пути (фильтр «тип» по решению владельца)
  const availableFormats = useMemo(() => {
    const set = new Set<string>();
    for (const d of docs) {
      const m = d.path.match(/\.([A-Za-z0-9]+)$/);
      if (m) set.add(m[1].toLowerCase());
    }
    return [...set].sort();
  }, [docs]);

  const filteredDocs = useMemo(() => {
    if (!docFormat) return docs;
    return docs.filter((d) => {
      const m = d.path.match(/\.([A-Za-z0-9]+)$/);
      return m ? m[1].toLowerCase() === docFormat : false;
    });
  }, [docs, docFormat]);

  const totalPages = Math.max(1, Math.ceil(filteredDocs.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = filteredDocs.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const resetFilters = () => {
    setSourceId('');
    setDocFormat('');
    setSearch('');
    setPage(0);
  };

  return (
    <Page
      title="Документы"
      subtitle="База знаний · документы источников и их чанки"
      action={<OperationalRefreshButton loading={loading} onClick={load} />}
    >
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && (
        <>
          <BackendStrip
            backendInfo={backendInfo}
            storeName={storeName}
            totalDocuments={totalDocuments}
          />
          <div className="ac-layout ac-layout--docs">
            <div className="ac-col ac-col--sources">
              <div className="ac-col__head">
                <span className="ac-col__title">Документы ({totalDocuments ?? docs.length})</span>
              </div>
              <div className="ac-filters-row">
                <select
                  className="ac-search"
                  value={sourceId}
                  onChange={(e) => { setSourceId(e.target.value); setPage(0); }}
                  aria-label="Фильтр по источнику"
                >
                  <option value="">Все источники</option>
                  {sources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name?.trim() || s.identifier}
                    </option>
                  ))}
                </select>
                <select
                  className="ac-search"
                  value={docFormat}
                  onChange={(e) => { setDocFormat(e.target.value); setPage(0); }}
                  aria-label="Фильтр по формату файла"
                >
                  <option value="">Все форматы</option>
                  {availableFormats.map((f) => (
                    <option key={f} value={f}>.{f}</option>
                  ))}
                </select>
              </div>
              <input
                className="ac-search"
                placeholder="Поиск по пути или названию…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { setPage(0); load(); } }}
              />
              <div className="ac-pagination">
                <div className="ac-pagination__row">
                  <button type="button" className="logs-page-btn" onClick={() => setPage(safePage - 1)} disabled={safePage <= 0}>
                    ← Назад
                  </button>
                  <span className="ac-pagination__counter">Страница {safePage + 1} из {totalPages}</span>
                  <button type="button" className="logs-page-btn" onClick={() => setPage(safePage + 1)} disabled={safePage >= totalPages - 1}>
                    Вперёд →
                  </button>
                </div>
                <div className="ac-pagination__row ac-pagination__row--meta">
                  <span className="ac-pagination__total">Всего {filteredDocs.length}</span>
                  <button
                    type="button"
                    className="logs-page-btn logs-page-btn--muted"
                    onClick={resetFilters}
                    disabled={!sourceId && !docFormat && !search && safePage === 0}
                  >
                    Сброс
                  </button>
                </div>
              </div>
              <div className="ac-source-list">
                {pageItems.map((doc) => (
                  <button
                    key={doc.id}
                    className={`ac-source-item${doc.id === selectedId ? ' ac-source-item--selected' : ''}`}
                    onClick={() => setSelectedId(doc.id)}
                    type="button"
                  >
                    <span className="ac-source-item__line1">
                      <span className="ac-source-item__date">{formatDateTime(doc.updated_at || doc.fetched_at)}</span>
                      <IndexStatusBadge chunkCount={doc.chunk_count} />
                    </span>
                    <span className="ac-source-item__title">{doc.title}</span>
                    <span className="ac-source-item__params">
                      <span>{doc.chunk_count ?? '—'} чанков</span>
                      <span>·</span>
                      <span className="ac-mono">{doc.source_identifier}</span>
                    </span>
                  </button>
                ))}
                {!loading && pageItems.length === 0 && <div className="ac-hint">Документы не найдены</div>}
              </div>
            </div>

            <div className="ac-col ac-col--detail">
              {cardLoading && <Loading />}
              {!cardLoading && !card && (
                <div className="ac-hint">Выберите документ слева.</div>
              )}
              {card && (
                <div className="dc-panes">
                  <div className="dc-cards-grid">
                    <section className="ac-section">
                      <h3 className="ac-section__title">Паспорт</h3>
                      <dl className="dc-rows">
                        <div className="dc-row"><dt>ID</dt><dd className="ac-mono" title={card.id}>{card.id}</dd></div>
                        <div className="dc-row"><dt>Название</dt><dd title={card.passport.title}>{card.passport.title}</dd></div>
                        <div className="dc-row"><dt>Путь</dt><dd className="ac-mono" title={card.passport.path}>{card.passport.path}</dd></div>
                        <div className="dc-row"><dt>Источник</dt><dd>{card.passport.source_display_name ?? card.passport.source_identifier ?? '—'}</dd></div>
                        <div className="dc-row"><dt>URL</dt>
                          <dd>{card.passport.raw_url
                            ? <a className="dc-url" href={card.passport.raw_url} target="_blank" rel="noreferrer">{card.passport.raw_url}</a>
                            : '—'}</dd>
                        </div>
                        <div className="dc-row"><dt>Commit</dt><dd className="ac-mono">{card.operation.commit_sha ?? '—'}</dd></div>
                      </dl>
                    </section>

                    <section className="ac-section">
                      <h3 className="ac-section__title">Эксплуатация</h3>
                      <dl className="dc-rows">
                        <div className="dc-row"><dt>Чанки в бэкенде</dt><dd>{card.operation.backend_chunks ?? '—'}</dd></div>
                        <div className="dc-row"><dt>Статус</dt>
                          <dd>
                            <IndexStatusBadge chunkCount={card.operation.backend_chunks} />
                          </dd>
                        </div>
                        <div className="dc-row"><dt>Объём</dt><dd>{card.passport.content_length.toLocaleString('ru-RU')} симв.</dd></div>
                        <div className="dc-row"><dt>Загружено</dt><dd>{formatDateTime(card.operation.fetched_at)}</dd></div>
                        <div className="dc-row"><dt>Обновлено</dt><dd>{formatDateTime(card.operation.updated_at)}</dd></div>
                      </dl>
                    </section>
                  </div>

                  <section className="ac-section">
                    <div className="ac-section__head">
                      <h3 className="ac-section__title">Preview текста</h3>
                      <button
                        className="admin-btn admin-btn--small"
                        type="button"
                        onClick={openText}
                        disabled={textLoading}
                      >
                        {textLoading ? 'Открываю…' : 'Открыть'}
                      </button>
                    </div>
                    {card.passport.content_length > 0 && (
                      <p className="dc-counter">
                        {card.text_preview_length} / {card.passport.content_length}
                      </p>
                    )}
                    <pre className="dc-text-preview">
                      {card.text_preview}
                      {card.text_truncated ? '\n…' : ''}
                    </pre>
                  </section>

                  <section className="ac-section ac-section--history">
                    <div className="ac-section__head">
                      <h3 className="ac-section__title">Чанки ({chunks.length})</h3>
                    </div>
                    {chunksLoading && <Loading />}
                    <div className="dc-chunk-list">
                      {chunks.map((chunk) => (
                        <ChunkCard key={`${chunk.id ?? 'idx'}-${chunk.chunk_index ?? 'x'}`} chunk={chunk} />
                      ))}
                      {!chunksLoading && chunks.length === 0 && (
                        <div className="ac-hint">Чанков в активном бэкенде нет.</div>
                      )}
                    </div>
                  </section>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {fullText && (
        <Modal title={fullText.title} onClose={() => setFullText(null)}>
          <p className="ac-card__muted ac-mono">{fullText.path}</p>
          <pre className="dc-text-full">{fullText.text}</pre>
        </Modal>
      )}
    </Page>
  );
}

/* Чанк по канону AIC: #[index] · длина, справа «Раскрыть/Свернуть»,
   свёрнуто — три строки (line-clamp). */
function ChunkCard({ chunk }: { chunk: DocumentChunk }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="dc-chunk">
      <div className="dc-chunk__head">
        <span className="ac-card__muted">
          #{chunk.chunk_index ?? '—'} · {chunk.chunk_length ?? '—'} симв.
        </span>
        <button className="dc-chunk__toggle" type="button" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Свернуть' : 'Раскрыть'}
        </button>
      </div>
      <div className={`dc-chunk__preview${expanded ? ' dc-chunk__preview--open' : ''}`}>{chunk.preview}</div>
    </div>
  );
}