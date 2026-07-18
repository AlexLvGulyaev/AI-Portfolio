import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Table } from '../components/Table';
import {
  listLogs,
  type OperationalLog,
} from '../api/client';

const LOG_PAGE_SIZE = 20;

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
}

function truncate(text: string | null, max = 80) {
  if (!text) return '—';
  return text.length > max ? text.slice(0, max) + '…' : text;
}

// ------------------------------------------------------------------
// LogsTab
// ------------------------------------------------------------------

function LogsTab() {
  const [logs, setLogs] = useState<OperationalLog[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState({
    event_type: '',
    status: '',
    date_from: '',
    date_to: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedLog, setSelectedLog] = useState<OperationalLog | null>(null);

  const load = () => {
    setLoading(true);
    setError('');
    listLogs({
      ...filters,
      limit: LOG_PAGE_SIZE,
      offset,
    })
      .then((res) => {
        setLogs(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load logs'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const applyFilters = () => {
    setOffset(0);
    load();
  };

  const totalPages = Math.ceil(total / LOG_PAGE_SIZE);
  const currentPage = Math.floor(offset / LOG_PAGE_SIZE) + 1;

  const columns = [
    { key: 'created_at', header: 'Время', render: (row: OperationalLog) => formatDate(row.created_at) },
    { key: 'event_type', header: 'Событие' },
    { key: 'status', header: 'Статус' },
    { key: 'provider_key', header: 'Провайдер', render: (row: OperationalLog) => row.provider_key || '—' },
    { key: 'query', header: 'Запрос', render: (row: OperationalLog) => truncate(row.query) },
    {
      key: 'actions',
      header: 'Действия',
      render: (row: OperationalLog) => (
        <button
          className="admin-btn admin-btn--small"
          type="button"
          onClick={() => setSelectedLog(row)}
        >
          Детали
        </button>
      ),
    },
  ];

  return (
    <div>
      <Card className="admin-form-card">
        <div className="admin-filters">
          <label className="admin-form__field">
            <span>Тип события</span>
            <input
              type="text"
              value={filters.event_type}
              onChange={(e) => setFilters((f) => ({ ...f, event_type: e.target.value }))}
              placeholder="chat_request"
            />
          </label>
          <label className="admin-form__field">
            <span>Статус</span>
            <select
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="">Все</option>
              <option value="ok">ok</option>
              <option value="error">error</option>
            </select>
          </label>
          <label className="admin-form__field">
            <span>Дата с</span>
            <input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
            />
          </label>
          <label className="admin-form__field">
            <span>Дата по</span>
            <input
              type="date"
              value={filters.date_to}
              onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
            />
          </label>
          <button className="admin-btn admin-btn--primary" type="button" onClick={applyFilters}>
            Применить
          </button>
        </div>
      </Card>

      {error && <ErrorState message={error} onRetry={load} />}
      {loading && <Loading />}
      {!loading && logs.length === 0 && !error && <EmptyState message="Нет логов" />}
      {!loading && logs.length > 0 && !error && (
        <>
          <Table columns={columns} rows={logs} keyExtractor={(row) => row.id} />
          {totalPages > 1 && (
            <div className="admin-pagination">
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - LOG_PAGE_SIZE))}
              >
                ← Назад
              </button>
              <span className="admin-pagination__info">
                Страница {currentPage} из {totalPages} ({total} всего)
              </span>
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset + LOG_PAGE_SIZE >= total}
                onClick={() => setOffset((o) => o + LOG_PAGE_SIZE)}
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}

      {selectedLog && (
        <div className="admin-dialog-overlay" onClick={() => setSelectedLog(null)}>
          <div className="admin-dialog admin-dialog--wide" onClick={(e) => e.stopPropagation()}>
            <h3 className="admin-dialog__title">Детали лога</h3>
            <dl className="admin-detail-list">
              <dt>ID</dt><dd>{selectedLog.id}</dd>
              <dt>Тип события</dt><dd>{selectedLog.event_type}</dd>
              <dt>Статус</dt><dd>{selectedLog.status}</dd>
              <dt>Провайдер</dt><dd>{selectedLog.provider_key || '—'}</dd>
              <dt>Модель</dt><dd>{selectedLog.model_name || '—'}</dd>
              <dt>Время ответа</dt><dd>{selectedLog.response_time_ms ?? '—'} мс</dd>
              <dt>Из кеша</dt><dd>{selectedLog.from_cache ? 'Да' : 'Нет'}</dd>
              <dt>Создан</dt><dd>{formatDate(selectedLog.created_at)}</dd>
            </dl>
            <div className="admin-detail-block">
              <h4>Запрос</h4>
              <pre className="admin-code">{selectedLog.query || '—'}</pre>
            </div>
            <div className="admin-detail-block">
              <h4>Ответ</h4>
              <pre className="admin-code">{selectedLog.response || '—'}</pre>
            </div>
            {selectedLog.error_message && (
              <div className="admin-detail-block">
                <h4>Ошибка</h4>
                <pre className="admin-code">{selectedLog.error_message}</pre>
              </div>
            )}
            <div className="admin-dialog__actions">
              <button className="admin-btn admin-btn--secondary" onClick={() => setSelectedLog(null)} type="button">
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function LogsPage() {
  return (
    <Page title="Логи">
      <LogsTab />
    </Page>
  );
}
