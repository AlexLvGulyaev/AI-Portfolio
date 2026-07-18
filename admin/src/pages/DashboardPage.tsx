import { useEffect, useMemo, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import {
  getDashboard,
  listAIProviders,
  updateAIProvider,
  activateAIProvider,
  setFallbackAIProvider,
  testAIProvider,
  type DashboardData,
  type AIProvider,
  type AIProviderUpdate,
  type AIProviderTestResult,
} from '../api/client';

const GIGACHAT_MODELS = new Set(['GigaChat', 'GigaChat-Max', 'GigaChat-Pro', 'GigaChat-Plus']);

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

interface ProviderEdit {
  model_name: string;
  base_url: string;
  temperature: string;
  max_tokens: string;
  is_enabled: boolean;
}

function editFromProvider(provider: AIProvider): ProviderEdit {
  return {
    model_name: provider.model_name || '',
    base_url: provider.base_url || provider.effective_base_url || '',
    temperature: provider.temperature != null ? String(provider.temperature) : '',
    max_tokens: provider.max_tokens != null ? String(provider.max_tokens) : '',
    is_enabled: provider.is_enabled,
  };
}

function validateProviderEdit(provider: AIProvider, edit: ProviderEdit): Record<string, string> {
  const errors: Record<string, string> = {};

  const model = edit.model_name.trim();
  if (!model) {
    errors.model_name = 'Укажите модель';
  } else if (model.length > 128) {
    errors.model_name = 'Слишком длинное имя модели';
  } else if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(model)) {
    errors.model_name = 'Допустимы латиница, цифры, точка, дефис и подчёркивание';
  } else if (provider.provider_key === 'gigachat' && !GIGACHAT_MODELS.has(model)) {
    errors.model_name = `Допустимо: ${[...GIGACHAT_MODELS].join(', ')}`;
  }

  if (edit.temperature !== '') {
    const t = Number(edit.temperature);
    if (Number.isNaN(t) || t < 0 || t > 2) {
      errors.temperature = 'Допустимо от 0 до 2';
    }
  }

  if (edit.max_tokens !== '') {
    const n = Number(edit.max_tokens);
    if (Number.isNaN(n) || !Number.isInteger(n) || n < 1) {
      errors.max_tokens = 'Целое число ≥ 1';
    }
  }

  return errors;
}

interface ProviderCardProps {
  provider: AIProvider;
  edit: ProviderEdit;
  fieldErrors: Record<string, string>;
  saveFlash: boolean;
  testResult: AIProviderTestResult | null;
  saving: boolean;
  onEditChange: (edit: ProviderEdit) => void;
  onSave: () => void;
  onTest: () => void;
}

function ProviderCard({
  provider,
  edit,
  fieldErrors,
  saveFlash,
  testResult,
  saving,
  onEditChange,
  onSave,
  onTest,
}: ProviderCardProps) {
  const disabled = saving || provider.implementation_status === 'not_implemented';
  const isGigachat = provider.provider_key === 'gigachat';

  return (
    <Card className="provider-card">
      <div className="provider-card__header">
        <span className="provider-card__name">{provider.display_name}</span>
        {provider.is_active && <span className="admin-status admin-status--ok">ACTIVE</span>}
        {provider.is_fallback && <span className="admin-status admin-status--info">FALLBACK</span>}
        {!provider.is_enabled && <span className="admin-status admin-status--warning">OFF</span>}
        {provider.readiness === 'ready' && provider.is_enabled && (
          <span className="admin-status admin-status--ok">READY</span>
        )}
      </div>
      <div className="provider-card__body provider-card__body--form">
        <label className={`provider-card__control ${fieldErrors.base_url ? 'provider-card__control--error' : ''}`}>
          <span>Base URL / Endpoint</span>
          <input
            type="text"
            value={edit.base_url}
            placeholder={provider.effective_base_url || '—'}
            onChange={(e) => onEditChange({ ...edit, base_url: e.target.value })}
            disabled={disabled}
            aria-invalid={Boolean(fieldErrors.base_url)}
          />
          {fieldErrors.base_url && <span className="provider-card__error">{fieldErrors.base_url}</span>}
        </label>
        <label className={`provider-card__control ${fieldErrors.model_name ? 'provider-card__control--error' : ''}`}>
          <span>Model {isGigachat && <span className="provider-card__hint">GigaChat / Max / Pro / Plus</span>}</span>
          <input
            type="text"
            value={edit.model_name}
            onChange={(e) => onEditChange({ ...edit, model_name: e.target.value })}
            disabled={disabled}
            aria-invalid={Boolean(fieldErrors.model_name)}
          />
          {fieldErrors.model_name && <span className="provider-card__error">{fieldErrors.model_name}</span>}
        </label>
        <div className="provider-card__row">
          <label className={`provider-card__control ${fieldErrors.temperature ? 'provider-card__control--error' : ''}`}>
            <span>Temperature</span>
            <input
              type="number"
              step="0.05"
              min="0"
              max="2"
              value={edit.temperature}
              onChange={(e) => onEditChange({ ...edit, temperature: e.target.value })}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.temperature)}
            />
            {fieldErrors.temperature && <span className="provider-card__error">{fieldErrors.temperature}</span>}
          </label>
          <label className={`provider-card__control ${fieldErrors.max_tokens ? 'provider-card__control--error' : ''}`}>
            <span>Max tokens</span>
            <input
              type="number"
              min="1"
              value={edit.max_tokens}
              onChange={(e) => onEditChange({ ...edit, max_tokens: e.target.value })}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.max_tokens)}
            />
            {fieldErrors.max_tokens && <span className="provider-card__error">{fieldErrors.max_tokens}</span>}
          </label>
        </div>
        <label className="provider-card__control provider-card__control--inline">
          <span>{edit.is_enabled ? 'Включён' : 'Отключён'}</span>
          <input
            type="checkbox"
            checked={edit.is_enabled}
            onChange={(e) => onEditChange({ ...edit, is_enabled: e.target.checked })}
            disabled={disabled}
            aria-label={edit.is_enabled ? 'Включён' : 'Отключён'}
          />
        </label>
        {provider.missing_env_keys.length > 0 && (
          <p className="provider-card__warning">
            Не заданы env: {provider.missing_env_keys.join(', ')}
          </p>
        )}
        {testResult && (
          <p className={`provider-card__test ${testResult.ok ? 'provider-card__test--ok' : 'provider-card__test--error'}`}>
            {testResult.ok ? '✓' : '✗'} {testResult.message}
          </p>
        )}
      </div>
      <div className="provider-card__foot">
        <button
          className="admin-btn admin-btn--small"
          type="button"
          disabled={disabled}
          onClick={onSave}
        >
          {saving ? 'Сохранение…' : 'Сохранить'}
        </button>
        <button
          className="admin-btn admin-btn--small admin-btn--secondary"
          type="button"
          disabled={disabled}
          onClick={onTest}
        >
          Проверить
        </button>
        {saveFlash && <span className="provider-card__flash">Сохранено</span>}
      </div>
    </Card>
  );
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const [edits, setEdits] = useState<Record<string, ProviderEdit>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, Record<string, string>>>({});
  const [saveFlash, setSaveFlash] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, AIProviderTestResult | null>>({});

  const [activeKey, setActiveKey] = useState('');
  const [fallbackKey, setFallbackKey] = useState('');
  const [routingError, setRoutingError] = useState('');
  const [routingFlash, setRoutingFlash] = useState(false);

  const providers = useMemo(() => data?.ai_providers.providers || [], [data]);

  const load = () => {
    setLoading(true);
    setError('');
    Promise.all([getDashboard(), listAIProviders()])
      .then(([dashboard, providerList]) => {
        setData(dashboard);
        const nextEdits: Record<string, ProviderEdit> = {};
        for (const p of providerList) {
          nextEdits[p.provider_key] = editFromProvider(p);
        }
        setEdits(nextEdits);
        setFieldErrors({});

        const active = providerList.find((p) => p.is_active);
        const fallback = providerList.find((p) => p.is_fallback);
        setActiveKey(active?.provider_key || '');
        setFallbackKey(fallback?.provider_key || '');
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

  function patchEdit(key: string, next: ProviderEdit) {
    setEdits((prev) => ({ ...prev, [key]: next }));
    setFieldErrors((prev) => {
      const errs = { ...(prev[key] || {}) };
      delete errs.model_name;
      delete errs.base_url;
      delete errs.temperature;
      delete errs.max_tokens;
      return { ...prev, [key]: errs };
    });
  }

  async function saveProvider(provider: AIProvider) {
    const key = provider.provider_key;
    const edit = edits[key];
    if (!edit) return;

    const errors = validateProviderEdit(provider, edit);
    if (Object.keys(errors).length > 0) {
      setFieldErrors((prev) => ({ ...prev, [key]: errors }));
      return;
    }

    setActionLoading(true);
    setFieldErrors((prev) => ({ ...prev, [key]: {} }));
    setRoutingError('');
    try {
      const body: AIProviderUpdate = {
        model_name: edit.model_name.trim(),
        base_url: edit.base_url.trim() || null,
        is_enabled: edit.is_enabled,
        temperature: edit.temperature === '' ? null : Number(edit.temperature),
        max_tokens: edit.max_tokens === '' ? null : Number(edit.max_tokens),
      };
      const updated = await updateAIProvider(key, body);
      const snap = editFromProvider(updated);
      setEdits((prev) => ({ ...prev, [key]: snap }));
      setSaveFlash((prev) => ({ ...prev, [key]: true }));
      setTimeout(() => {
        setSaveFlash((prev) => ({ ...prev, [key]: false }));
      }, 1800);
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setFieldErrors((prev) => ({ ...prev, [key]: { general: message } }));
    } finally {
      setActionLoading(false);
    }
  }

  async function runTest(provider: AIProvider) {
    const key = provider.provider_key;
    setActionLoading(true);
    setTestResults((prev) => ({ ...prev, [key]: null }));
    try {
      const result = await testAIProvider(key);
      setTestResults((prev) => ({ ...prev, [key]: result }));
      await load();
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [key]: {
          provider_key: key,
          ok: false,
          readiness: 'error',
          message: err instanceof Error ? err.message : 'Unknown error',
          missing_env_keys: [],
          implementation_status: provider.implementation_status,
        },
      }));
    } finally {
      setActionLoading(false);
    }
  }

  async function saveRouting() {
    if (!activeKey) {
      setRoutingError('Выберите активного провайдера');
      return;
    }
    setActionLoading(true);
    setRoutingError('');
    try {
      await activateAIProvider(activeKey);
      if (fallbackKey && fallbackKey !== activeKey) {
        await setFallbackAIProvider(fallbackKey);
      }
      setRoutingFlash(true);
      setTimeout(() => setRoutingFlash(false), 1800);
      await load();
    } catch (err) {
      setRoutingError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setActionLoading(false);
    }
  }

  return (
    <Page
      title="Системные настройки"
      subtitle="Runtime health, LLM-провайдеры, контент и операции"
      action={
        <button className="admin-btn admin-btn--small" onClick={load} type="button" disabled={loading || actionLoading}>
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
            <div className="dashboard-grid dashboard-grid--3">
              <MetricCard label="API" value={<StatusBadge status={data.system.backend} />} />
              <MetricCard label="PostgreSQL" value={<StatusBadge status={data.system.postgresql} />} />
              <MetricCard label="ChromaDB" value={<StatusBadge status={data.system.chromadb} />} />
            </div>
          </Card>

          <div className="dashboard-bottom">
            <Card className="dashboard-section dashboard-section--compact dashboard-section--providers">
              <h2 className="dashboard-section__title">LLM-провайдеры и активность</h2>
              <p className="dashboard-section__subtitle">Активный / fallback провайдер и карточки провайдеров.</p>

              <div className="provider-routing">
                <div className="provider-routing__row">
                  <label className="provider-routing__field">
                    <span>Активный</span>
                    <select
                      value={activeKey}
                      onChange={(e) => setActiveKey(e.target.value)}
                      disabled={actionLoading}
                    >
                      <option value="">— выберите —</option>
                      {providers.map((p) => (
                        <option key={p.provider_key} value={p.provider_key} disabled={!p.is_enabled}>
                          {p.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="provider-routing__field">
                    <span>Fallback</span>
                    <select
                      value={fallbackKey}
                      onChange={(e) => setFallbackKey(e.target.value)}
                      disabled={actionLoading}
                    >
                      <option value="">—</option>
                      {providers.map((p) => (
                        <option key={p.provider_key} value={p.provider_key} disabled={!p.is_enabled}>
                          {p.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="provider-routing__actions">
                    <button
                      className="admin-btn admin-btn--small"
                      type="button"
                      disabled={actionLoading || !activeKey}
                      onClick={saveRouting}
                    >
                      Сохранить
                    </button>
                    {routingFlash && <span className="provider-card__flash">Сохранено</span>}
                  </div>
                </div>
                {routingError && <p className="provider-routing__error">{routingError}</p>}
              </div>

              <div className="dashboard-grid dashboard-grid--2 dashboard-grid--providers">
                {providers.map((provider) => (
                  <ProviderCard
                    key={provider.provider_key}
                    provider={provider}
                    edit={edits[provider.provider_key] || editFromProvider(provider)}
                    fieldErrors={fieldErrors[provider.provider_key] || {}}
                    saveFlash={Boolean(saveFlash[provider.provider_key])}
                    testResult={testResults[provider.provider_key] || null}
                    saving={actionLoading}
                    onEditChange={(next) => patchEdit(provider.provider_key, next)}
                    onSave={() => saveProvider(provider)}
                    onTest={() => runTest(provider)}
                  />
                ))}
              </div>
            </Card>

            <div className="dashboard-grid dashboard-grid--2 dashboard-grid--vertical">
              <Card className="dashboard-section dashboard-section--compact">
                <h2 className="dashboard-section__title">Контент</h2>
                <p className="dashboard-section__subtitle">Карточки, KB-источники и синхронизация.</p>
                <div className="dashboard-grid dashboard-grid--2">
                  <MetricCard label="Карточки проектов" value={data.project_cards.total} note={`видимых ${data.project_cards.visible}`} />
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

              <Card className="dashboard-section dashboard-section--compact">
                <h2 className="dashboard-section__title">Операции</h2>
                <p className="dashboard-section__subtitle">Журналы, диалоги и обновление.</p>
                <div className="dashboard-grid dashboard-grid--2">
                  <MetricCard label="Логи" value={data.logs.total} />
                  <MetricCard label="Диалоги" value={data.conversations.total} />
                  <MetricCard label="Активные диалоги" value={data.conversations.active} />
                  <MetricCard label="Updated" value={new Date(data.timestamp).toLocaleString('ru-RU')} />
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}
    </Page>
  );
}
