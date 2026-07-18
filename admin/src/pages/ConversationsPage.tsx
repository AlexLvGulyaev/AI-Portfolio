import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Table } from '../components/Table';
import {
  listConversations,
  getConversation,
  type ChatSession,
  type ConversationDetail,
} from '../api/client';

const CONV_PAGE_SIZE = 20;

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
}

export function ConversationsPage() {
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
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить диалоги'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset]);

  const openConversation = (id: string) => {
    getConversation(id)
      .then(setSelected)
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить диалог'));
  };

  const totalPages = Math.ceil(total / CONV_PAGE_SIZE);
  const currentPage = Math.floor(offset / CONV_PAGE_SIZE) + 1;

  const columns = [
    { key: 'created_at', header: 'Начат', render: (row: ChatSession) => formatDate(row.created_at) },
    { key: 'mode', header: 'Режим' },
    {
      key: 'active',
      header: 'Активен',
      render: (row: ChatSession) => (row.is_active ? 'Да' : 'Нет'),
    },
    {
      key: 'actions',
      header: 'Действия',
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
    <Page title="Диалоги">
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
            <h3 className="admin-dialog__title">Сообщения диалога ({selected.message_count})</h3>
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
    </Page>
  );
}
