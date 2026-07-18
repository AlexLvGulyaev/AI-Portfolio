import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Table } from '../components/Table';
import {
  listLogs,
  listConversations,
  getConversation,
  type OperationalLog,
  type ChatSession,
  type ConversationDetail,
} from '../api/client';

type TabId = 'logs' | 'conversations';

const TABS: { id: TabId; label: string }[] = [
  { id: 'logs', label: 'Operational Logs' },
  { id: 'conversations', label: 'Conversations' },
];

const LOG_PAGE_SIZE = 20;
const CONV_PAGE_SIZE = 20;

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
    { key: 'created_at', header: 'Time', render: (row: OperationalLog) => formatDate(row.created_at) },
    { key: 'event_type', header: 'Event' },
    { key: 'status', header: 'Status' },
    { key: 'provider_key', header: 'Provider', render: (row: OperationalLog) => row.provider_key || '—' },
    { key: 'query', header: 'Query', render: (row: OperationalLog) => truncate(row.query) },
    {
      key: 'actions',
      header: 'Actions',
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
            <span>Event Type</span>
            <input
              type="text"
              value={filters.event_type}
              onChange={(e) => setFilters((f) => ({ ...f, event_type: e.target.value }))}
              placeholder="chat_request"
            />
          </label>
          <label className="admin-form__field">
            <span>Status</span>
            <select
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="">All</option>
              <option value="ok">ok</option>
              <option value="error">error</option>
            </select>
          </label>
          <label className="admin-form__field">
            <span>Date From</span>
            <input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
            />
          </label>
          <label className="admin-form__field">
            <span>Date To</span>
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
            <h3 className="admin-dialog__title">Log Detail</h3>
            <dl className="admin-detail-list">
              <dt>ID</dt><dd>{selectedLog.id}</dd>
              <dt>Event Type</dt><dd>{selectedLog.event_type}</dd>
              <dt>Status</dt><dd>{selectedLog.status}</dd>
              <dt>Provider</dt><dd>{selectedLog.provider_key || '—'}</dd>
              <dt>Model</dt><dd>{selectedLog.model_name || '—'}</dd>
              <dt>Response Time</dt><dd>{selectedLog.response_time_ms ?? '—'} ms</dd>
              <dt>From Cache</dt><dd>{selectedLog.from_cache ? 'Yes' : 'No'}</dd>
              <dt>Created At</dt><dd>{formatDate(selectedLog.created_at)}</dd>
            </dl>
            <div className="admin-detail-block">
              <h4>Query</h4>
              <pre className="admin-code">{selectedLog.query || '—'}</pre>
            </div>
            <div className="admin-detail-block">
              <h4>Response</h4>
              <pre className="admin-code">{selectedLog.response || '—'}</pre>
            </div>
            {selectedLog.error_message && (
              <div className="admin-detail-block">
                <h4>Error</h4>
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

// ------------------------------------------------------------------
// ConversationsTab
// ------------------------------------------------------------------

function ConversationsTab() {
  const [conversations, setConversations] = useState<ChatSession[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ConversationDetail | null>(null);

  const load = () => {
    setLoading(true);
    setError('');
    listConversations({ limit: CONV_PAGE_SIZE, offset })
      .then((res) => {
        setConversations(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load conversations'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const openConversation = (id: string) => {
    getConversation(id)
      .then(setSelected)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load conversation'));
  };

  const totalPages = Math.ceil(total / CONV_PAGE_SIZE);
  const currentPage = Math.floor(offset / CONV_PAGE_SIZE) + 1;

  const columns = [
    { key: 'created_at', header: 'Started', render: (row: ChatSession) => formatDate(row.created_at) },
    { key: 'mode', header: 'Mode' },
    {
      key: 'active',
      header: 'Active',
      render: (row: ChatSession) => (row.is_active ? 'Yes' : 'No'),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row: ChatSession) => (
        <button
          className="admin-btn admin-btn--small"
          type="button"
          onClick={() => openConversation(row.id)}
        >
          Сообщения
        </button>
      ),
    },
  ];

  return (
    <div>
      {error && <ErrorState message={error} onRetry={load} />}
      {loading && <Loading />}
      {!loading && conversations.length === 0 && !error && <EmptyState message="Нет диалогов" />}
      {!loading && conversations.length > 0 && !error && (
        <>
          <Table columns={columns} rows={conversations} keyExtractor={(row) => row.id} />
          {totalPages > 1 && (
            <div className="admin-pagination">
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - CONV_PAGE_SIZE))}
              >
                ← Назад
              </button>
              <span className="admin-pagination__info">
                Страница {currentPage} из {totalPages} ({total} всего)
              </span>
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset + CONV_PAGE_SIZE >= total}
                onClick={() => setOffset((o) => o + CONV_PAGE_SIZE)}
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}

      {selected && (
        <div className="admin-dialog-overlay" onClick={() => setSelected(null)}>
          <div className="admin-dialog admin-dialog--wide" onClick={(e) => e.stopPropagation()}>
            <h3 className="admin-dialog__title">Conversation Messages ({selected.message_count})</h3>
            <div className="admin-messages">
              {selected.messages.length === 0 && <EmptyState message="Нет сообщений" />}
              {selected.messages.map((msg) => (
                <div key={msg.id} className={`admin-message admin-message--${msg.role}`}>
                  <div className="admin-message__meta">
                    <strong>{msg.role}</strong>
                    <span>{formatDate(msg.created_at)}</span>
                  </div>
                  <div className="admin-message__content">{msg.content}</div>
                </div>
              ))}
            </div>
            <div className="admin-dialog__actions">
              <button className="admin-btn admin-btn--secondary" onClick={() => setSelected(null)} type="button">
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
  const [activeTab, setActiveTab] = useState<TabId>('logs');

  return (
    <Page title="Logs / Conversations">
      <div className="admin-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`admin-tab${activeTab === tab.id ? ' admin-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="admin-tab-panel">
        {activeTab === 'logs' && <LogsTab />}
        {activeTab === 'conversations' && <ConversationsTab />}
      </div>
    </Page>
  );
}
