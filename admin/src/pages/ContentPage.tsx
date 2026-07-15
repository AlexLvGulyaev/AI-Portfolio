import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { getKnowledgeBaseStatus } from '../api/client';

export function ContentPage() {
  const [data, setData] = useState<{ status: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    getKnowledgeBaseStatus()
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
    <Page title="Content / Knowledge Base">
      {loading && <Loading />}
      {error && <ErrorState message={error} onRetry={load} />}
      {data && !loading && !error && (
        <div>
          <p>Рабочее пространство: Content / Knowledge Base</p>
          <p>Backend status: {data.status}</p>
        </div>
      )}
    </Page>
  );
}
