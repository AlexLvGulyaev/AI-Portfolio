import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { getDashboard, type DashboardData } from '../api/client';
import { formatTimestampLocal } from '../utils/operationalLabels';

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  let variant = 'error';
  if (['ok', 'ready', 'normal', 'norma', 'success'].includes(normalized)) {
    variant = 'ok';
  } else if (normalized === 'pending' || normalized.startsWith('degraded')) {
    variant = 'warning';
  }

  let label = status;
  if (['ok', 'ready', 'normal', 'norma'].includes(normalized)) {
    label = 'НОРМА';
  }

  return <span className={`admin-status admin-status--${variant}`}>{label}</span>;
}

function MetricCard({ label, value, note }: { label: string; value: React.ReactNode; note?: string }) {
  return (
    <Card className="dashboard-metric">
      <div className="dashboard-metric__label">{label}</div>
      <div className="dashboard-metric__value">{value}</div>
      {note && <div className="dashboard-metric__note">{note}</div>}
    </Card>
  );
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    getDashboard()
      .then(setData)
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Unknown error');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Page
      title="Обзор"
      subtitle="Состояние бэкендов, контент и операции"
      action={
        <button className="admin-btn admin-btn--small" onClick={load} type="button" disabled={loading}>
          Обновить
        </button>
      }
    >
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={load} />}
      {data && !loading && !error && (
        <div className="dashboard">
          <Card className="dashboard-section dashboard-section--compact dashboard-section--system">
            <h2 className="dashboard-section__title">Состояние системы</h2>
            <p className="dashboard-section__subtitle">Runtime health, зависимости и оперативный статус.</p>
            <div className="dashboard-grid dashboard-grid--4">
              <MetricCard label="API" value={<StatusBadge status={data.system.backend} />} />
              <MetricCard label="PostgreSQL" value={<StatusBadge status={data.system.postgresql} />} />
              <MetricCard
                label="ChromaDB"
                value={<StatusBadge status={data.system.chromadb} />}
                note={data.knowledge_base.chroma_chunks != null ? `чанков ${data.knowledge_base.chroma_chunks}` : undefined}
              />
              <MetricCard
                label="Weaviate"
                value={<StatusBadge status={data.system.weaviate} />}
                note={data.knowledge_base.chunks != null ? `чанков ${data.knowledge_base.chunks}` : undefined}
              />
            </div>
          </Card>

          <div className="dashboard-bottom">
            <Card className="dashboard-section dashboard-section--compact">
              <h2 className="dashboard-section__title">Контент</h2>
              <p className="dashboard-section__subtitle">Карточки, KB-источники, документы и синхронизация.</p>
              <div className="dashboard-grid dashboard-grid--2">
                <MetricCard label="Карточки проектов" value={data.project_cards.total} note={`видимых ${data.project_cards.visible}`} />
                <MetricCard label="On Homepage" value={data.project_cards.homepage} />
                <MetricCard label="KB Sources" value={data.knowledge_base.sources} />
                <MetricCard label="Документы" value={data.knowledge_base.documents} />
                <MetricCard
                  label="Last Sync"
                  value={
                    data.knowledge_base.last_sync_at
                      ? formatTimestampLocal(data.knowledge_base.last_sync_at)
                      : '—'
                  }
                  note={data.knowledge_base.last_sync_status}
                />
              </div>
            </Card>

            <Card className="dashboard-section dashboard-section--compact">
              <h2 className="dashboard-section__title">Операции</h2>
              <p className="dashboard-section__subtitle">Аудит, журналы, диалоги и обновление.</p>
              <div className="dashboard-grid dashboard-grid--2">
                <MetricCard label="Логи" value={data.logs.total} />
                <MetricCard label="Аудит" value={data.audit.total} />
                <MetricCard label="Диалоги" value={data.conversations.total} />
                <MetricCard label="Активные диалоги" value={data.conversations.active} />
                <MetricCard label="Updated" value={formatTimestampLocal(data.timestamp)} />
              </div>
            </Card>
          </div>
        </div>
      )}
    </Page>
  );
}