import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { getChromaStatus, syncKnowledgeBase, type ChromaStatus, type SyncJob } from '../api/client';

export function KnowledgeSyncPage() {
  const [chromaStatus, setChromaStatus] = useState<ChromaStatus | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncJob | null>(null);
  const [error, setError] = useState('');

  const loadStatus = () => {
    getChromaStatus()
      .then(setChromaStatus)
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить статус ChromaDB'));
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSync = () => {
    setSyncLoading(true);
    setError('');
    syncKnowledgeBase()
      .then((res) => {
        setSyncResult(res);
        loadStatus();
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Синхронизация не удалась'))
      .finally(() => setSyncLoading(false));
  };

  return (
    <Page title="Синхронизация">
      {error && <ErrorState message={error} onRetry={loadStatus} />}
      <Card className="dashboard-section">
        <h2 className="dashboard-section__title">Статус ChromaDB</h2>
        {chromaStatus?.status === 'ok' && (
          <div className="dashboard-grid dashboard-grid--3">
            <div className="dashboard-metric">
              <div className="dashboard-metric__label">Статус</div>
              <div className="dashboard-metric__value">OK</div>
            </div>
            <div className="dashboard-metric">
              <div className="dashboard-metric__label">Коллекция</div>
              <div className="dashboard-metric__value">{chromaStatus.collection_name}</div>
            </div>
            <div className="dashboard-metric">
              <div className="dashboard-metric__label">Чанков</div>
              <div className="dashboard-metric__value">{chromaStatus.chunks ?? '—'}</div>
            </div>
          </div>
        )}
        {chromaStatus?.status === 'error' && (
          <ErrorState message={chromaStatus.error || 'ChromaDB недоступна'} />
        )}
        {!chromaStatus && <Loading />}
      </Card>

      <Card className="dashboard-section">
        <h2 className="dashboard-section__title">Ручная синхронизация</h2>
        <p className="admin-note">
          Перестраивает индекс ChromaDB из knowledge_base/knowledge.json и knowledge_content карточек проектов.
        </p>
        <button
          className="admin-btn admin-btn--primary"
          type="button"
          onClick={handleSync}
          disabled={syncLoading}
        >
          {syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}
        </button>
        {syncResult && (
          <div className="admin-sync-result">
            <p>
              <strong>Статус:</strong>{' '}
              <span className={`admin-sync-status admin-sync-status--${syncResult.status}`}>
                {syncResult.status}
              </span>
            </p>
            <p>
              <strong>Документов обработано:</strong> {syncResult.stats.documents_processed}
            </p>
            <p>
              <strong>Чанков создано:</strong> {syncResult.stats.chunks_created}
            </p>
            {syncResult.error_message && <ErrorState message={syncResult.error_message} />}
            {syncResult.stats.errors.length > 0 && (
              <div className="admin-error">
                <p>Ошибки:</p>
                <ul>
                  {syncResult.stats.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </Page>
  );
}
