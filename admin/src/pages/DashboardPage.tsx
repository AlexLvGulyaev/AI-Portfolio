import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { getDashboard, type DashboardData, type AIProvider } from '../api/client';

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

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="dashboard-section__header">
      <h2 className="dashboard-section__title">{title}</h2>
      {action}
    </div>
  );
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

function ProviderCard({ provider }: { provider: AIProvider }) {
  return (
    <Card className="provider-card">
      <div className="provider-card__header">
        <span className="provider-card__name">{provider.display_name}</span>
        {provider.is_active && <span className="admin-status admin-status--ok">ACTIVE</span>}
        {provider.is_fallback && <span className="admin-status admin-status--info">FALLBACK</span>}
        {!provider.is_enabled && <span className="admin-status admin-status--warning">OFF</span>}
      </div>
      <div className="provider-card__body">
        <div className="provider-card__field">
          <span>Model</span>
          <strong>{provider.model_name}</strong>
        </div>
        <div className="provider-card__field">
          <span>Base URL / Env</span>
          <strong>{provider.base_url_env_key || provider.api_key_env_key || '—'}</strong>
        </div>
        <div className="provider-card__field">
          <span>Temperature</span>
          <strong>{provider.temperature ?? '—'}</strong>
        </div>
        <div className="provider-card__field">
          <span>Max Tokens</span>
          <strong>{provider.max_tokens ?? '—'}</strong>
        </div>
      </div>
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
      .then((response) => {
        setData(response);
      })
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
    <Page title="Dashboard">
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={load} />}
      {data && !loading && !error && (
        <div className="dashboard">
          <Card className="dashboard-section">
            <SectionHeader
              title="Состояние системы"
              action={
                <button className="admin-btn admin-btn--small" onClick={load} type="button">
                  Обновить
                </button>
              }
            />
            <p className="dashboard-section__subtitle">Runtime health, зависимости и оперативный статус.</p>
            <div className="dashboard-grid dashboard-grid--3">
              <MetricCard label="API" value={<StatusBadge status={data.system.backend} />} />
              <MetricCard label="PostgreSQL" value={<StatusBadge status={data.system.postgresql} />} />
              <MetricCard label="ChromaDB" value={<StatusBadge status={data.system.chromadb} />} />
            </div>
          </Card>

          <Card className="dashboard-section">
            <SectionHeader title="LLM-провайдеры и активность" />
            <p className="dashboard-section__subtitle">Активный / fallback провайдер, карточки провайдеров и операционные метрики.</p>

            <div className="dashboard-grid dashboard-grid--2 dashboard-grid--providers-top">
              <div className="provider-summary-card">
                <div className="provider-summary-card__label">Активный провайдер</div>
                <div className="provider-summary-card__value">
                  {data.ai_providers.active?.display_name || '—'}
                </div>
                <div className="provider-summary-card__note">
                  {data.ai_providers.active?.model_name || 'не настроен'}
                </div>
              </div>
              <div className="provider-summary-card">
                <div className="provider-summary-card__label">Fallback провайдер</div>
                <div className="provider-summary-card__value">
                  {data.ai_providers.fallback?.display_name || '—'}
                </div>
                <div className="provider-summary-card__note">
                  {data.ai_providers.fallback?.model_name || 'не настроен'}
                </div>
              </div>
            </div>

            <div className="dashboard-grid dashboard-grid--providers">
              {data.ai_providers.providers.map((provider) => (
                <ProviderCard key={provider.id} provider={provider} />
              ))}
            </div>

            <div className="dashboard-grid dashboard-grid--4 dashboard-grid--activity">
              <MetricCard label="Всего провайдеров" value={data.ai_providers.total} />
              <MetricCard label="Enabled" value={data.ai_providers.enabled} />
              <MetricCard label="Токенов (sample)" value="—" note="не собирается в v1" />
              <MetricCard label="Средняя задержка" value="—" note="не собирается в v1" />
            </div>
          </Card>

          <div className="dashboard-grid dashboard-grid--2">
            <Card className="dashboard-section">
              <SectionHeader title="Контент" />
              <p className="dashboard-section__subtitle">Управляемые карточки, источники KB и синхронизация.</p>
              <div className="dashboard-grid dashboard-grid--2">
                <MetricCard label="Project Cards" value={data.project_cards.total} note={`видимых ${data.project_cards.visible}`} />
                <MetricCard label="On Homepage" value={data.project_cards.homepage} />
                <MetricCard label="KB Sources" value={data.knowledge_base.sources} />
                <MetricCard
                  label="Last Sync"
                  value={
                    data.knowledge_base.last_sync_at
                      ? new Date(data.knowledge_base.last_sync_at).toLocaleString('ru-RU')
                      : '—'
                  }
                  note={data.knowledge_base.last_sync_status}
                />
              </div>
            </Card>

            <Card className="dashboard-section">
              <SectionHeader title="Операции" />
              <p className="dashboard-section__subtitle">Журналы и диалоги.</p>
              <div className="dashboard-grid dashboard-grid--2">
                <MetricCard label="Operational Logs" value={data.logs.total} />
                <MetricCard label="Conversations" value={data.conversations.total} />
                <MetricCard label="Active Conversations" value={data.conversations.active} />
                <MetricCard label="Updated" value={new Date(data.timestamp).toLocaleString('ru-RU')} />
              </div>
            </Card>
          </div>
        </div>
      )}
    </Page>
  );
}
