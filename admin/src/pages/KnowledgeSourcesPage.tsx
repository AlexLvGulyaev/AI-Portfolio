import { useEffect, useState } from 'react';
import { Page } from '../components/Page';
import { Card } from '../components/Card';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Table } from '../components/Table';
import { Toolbar } from '../components/Toolbar';
import { ConfirmDialog } from '../components/ConfirmDialog';
import {
  listSources,
  createSource,
  updateSource,
  deleteSource,
  type KnowledgeSource,
  type KnowledgeSourceCreate,
} from '../api/client';

function KnowledgeSourceForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: KnowledgeSource;
  onSubmit: (data: KnowledgeSourceCreate) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<KnowledgeSourceCreate>({
    source_type: initial?.source_type || 'local_file',
    identifier: initial?.identifier || '',
    branch: initial?.branch || '',
    base_path: initial?.base_path || '',
    is_enabled: initial?.is_enabled ?? true,
  });

  const update = <K extends keyof KnowledgeSourceCreate>(key: K, value: KnowledgeSourceCreate[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(form);
  };

  return (
    <form className="admin-form" onSubmit={handleSubmit}>
      <label className="admin-form__field">
        <span>Тип источника *</span>
        <select
          value={form.source_type}
          onChange={(e) => update('source_type', e.target.value as KnowledgeSourceCreate['source_type'])}
        >
          <option value="github_repo">GitHub-репозиторий</option>
          <option value="local_directory">Локальная директория</option>
          <option value="local_file">Локальный файл</option>
        </select>
      </label>
      <label className="admin-form__field">
        <span>Идентификатор *</span>
        <input
          type="text"
          value={form.identifier}
          onChange={(e) => update('identifier', e.target.value)}
          required
          placeholder="owner/repo или /path/to/file"
        />
      </label>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Ветка (для GitHub)</span>
          <input
            type="text"
            value={form.branch || ''}
            onChange={(e) => update('branch', e.target.value)}
          />
        </label>
        <label className="admin-form__field">
          <span>Базовый путь</span>
          <input
            type="text"
            value={form.base_path || ''}
            onChange={(e) => update('base_path', e.target.value)}
          />
        </label>
      </div>
      <label className="admin-form__field admin-form__field--inline">
        <input
          type="checkbox"
          checked={form.is_enabled}
          onChange={(e) => update('is_enabled', e.target.checked)}
        />
        <span>Включён</span>
      </label>
      <div className="admin-form__actions">
        <button className="admin-btn admin-btn--secondary" type="button" onClick={onCancel}>
          Отмена
        </button>
        <button className="admin-btn admin-btn--primary" type="submit">
          {initial ? 'Сохранить' : 'Создать'}
        </button>
      </div>
    </form>
  );
}

export function KnowledgeSourcesPage() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError('');
    listSources()
      .then((res) => setSources(res.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить источники'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleSubmit = (data: KnowledgeSourceCreate) => {
    const promise = editingSource
      ? updateSource(editingSource.id, data)
      : createSource(data);
    promise
      .then(() => {
        setShowForm(false);
        setEditingSource(null);
        load();
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось сохранить источник'));
  };

  const handleDelete = () => {
    if (!deleteSourceId) return;
    deleteSource(deleteSourceId)
      .then(() => {
        setDeleteSourceId(null);
        load();
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось удалить источник'));
  };

  const columns = [
    { key: 'source_type', header: 'Тип' },
    { key: 'identifier', header: 'Идентификатор' },
    { key: 'branch', header: 'Ветка', render: (row: KnowledgeSource) => row.branch || '—' },
    { key: 'base_path', header: 'Путь', render: (row: KnowledgeSource) => row.base_path || '—' },
    {
      key: 'enabled',
      header: 'Включён',
      render: (row: KnowledgeSource) => (row.is_enabled ? 'Да' : 'Нет'),
    },
    {
      key: 'last_sync',
      header: 'Последняя синхронизация',
      render: (row: KnowledgeSource) => (
        <span className={`admin-sync-status admin-sync-status--${row.last_sync_status}`}>
          {row.last_sync_status}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Действия',
      render: (row: KnowledgeSource) => (
        <div className="admin-row-actions">
          <button
            className="admin-btn admin-btn--small"
            type="button"
            onClick={() => {
              setEditingSource(row);
              setShowForm(true);
            }}
          >
            Редактировать
          </button>
          <button
            className="admin-btn admin-btn--small admin-btn--danger"
            type="button"
            onClick={() => setDeleteSourceId(row.id)}
          >
            Удалить
          </button>
        </div>
      ),
    },
  ];

  return (
    <Page title="Источники знаний">
      <Toolbar>
        <button
          className="admin-btn admin-btn--primary"
          type="button"
          onClick={() => {
            setEditingSource(null);
            setShowForm(true);
          }}
        >
          + Добавить источник
        </button>
      </Toolbar>
      {error && <ErrorState message={error} onRetry={load} />}
      {showForm && (
        <Card className="admin-form-card">
          <h3>{editingSource ? 'Редактировать источник' : 'Новый источник'}</h3>
          <KnowledgeSourceForm
            initial={editingSource || undefined}
            onSubmit={handleSubmit}
            onCancel={() => {
              setShowForm(false);
              setEditingSource(null);
            }}
          />
        </Card>
      )}
      {loading && <Loading />}
      {!loading && sources.length === 0 && !error && <EmptyState message="Нет источников знаний" />}
      {!loading && sources.length > 0 && !error && (
        <Table columns={columns} rows={sources} keyExtractor={(row) => row.id} />
      )}
      {deleteSourceId && (
        <ConfirmDialog
          title="Удалить источник?"
          message="Это действие нельзя отменить."
          onConfirm={handleDelete}
          onCancel={() => setDeleteSourceId(null)}
        />
      )}
    </Page>
  );
}
