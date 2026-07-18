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
  listProjectCards,
  createProjectCard,
  updateProjectCard,
  deleteProjectCard,
  listSources,
  createSource,
  updateSource,
  deleteSource,
  getChromaStatus,
  syncKnowledgeBase,
  type ProjectCard,
  type ProjectCardCreate,
  type KnowledgeSource,
  type KnowledgeSourceCreate,
  type ChromaStatus,
  type SyncJob,
} from '../api/client';

type TabId = 'cards' | 'sources' | 'sync';

const TABS: { id: TabId; label: string }[] = [
  { id: 'cards', label: 'Project Cards' },
  { id: 'sources', label: 'Knowledge Sources' },
  { id: 'sync', label: 'Sync & Status' },
];

function TagsList({ tags }: { tags: string[] }) {
  if (!tags || tags.length === 0) return <span>—</span>;
  return (
    <div className="admin-tags">
      {tags.map((tag) => (
        <span key={tag} className="admin-tag">{tag}</span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------
// ProjectCardForm
// ------------------------------------------------------------------

function ProjectCardForm({
  initial,
  onSubmit,
  onCancel,
}: {
  initial?: ProjectCard;
  onSubmit: (data: ProjectCardCreate) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<ProjectCardCreate>({
    slug: initial?.slug || '',
    title: initial?.title || '',
    short_description: initial?.short_description || '',
    category: initial?.category || 'cases',
    tags: initial?.tags || [],
    display_order: initial?.display_order ?? 0,
    show_on_homepage: initial?.show_on_homepage ?? 0,
    is_visible: initial?.is_visible ?? true,
    knowledge_content: initial?.knowledge_content || '',
    external_url: initial?.external_url || '',
  });

  const update = <K extends keyof ProjectCardCreate>(key: K, value: ProjectCardCreate[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: ProjectCardCreate = {
      ...form,
      tags: typeof form.tags === 'string'
        ? (form.tags as unknown as string).split(',').map((t) => t.trim()).filter(Boolean)
        : form.tags,
    };
    onSubmit(data);
  };

  return (
    <form className="admin-form" onSubmit={handleSubmit}>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Slug *</span>
          <input
            type="text"
            value={form.slug}
            onChange={(e) => update('slug', e.target.value)}
            required
          />
        </label>
        <label className="admin-form__field">
          <span>Title *</span>
          <input
            type="text"
            value={form.title}
            onChange={(e) => update('title', e.target.value)}
            required
          />
        </label>
      </div>
      <label className="admin-form__field">
        <span>Short Description *</span>
        <textarea
          value={form.short_description}
          onChange={(e) => update('short_description', e.target.value)}
          rows={3}
          required
        />
      </label>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Category</span>
          <input
            type="text"
            value={form.category}
            onChange={(e) => update('category', e.target.value)}
          />
        </label>
        <label className="admin-form__field">
          <span>Tags (comma separated)</span>
          <input
            type="text"
            value={Array.isArray(form.tags) ? form.tags.join(', ') : form.tags}
            onChange={(e) => update('tags', e.target.value.split(',').map((t) => t.trim()).filter(Boolean) as never)}
          />
        </label>
      </div>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Display Order</span>
          <input
            type="number"
            value={form.display_order}
            onChange={(e) => update('display_order', Number(e.target.value))}
          />
        </label>
        <label className="admin-form__field">
          <span>Show on Homepage (0..4)</span>
          <input
            type="number"
            min={0}
            max={4}
            value={form.show_on_homepage}
            onChange={(e) => update('show_on_homepage', Number(e.target.value))}
          />
        </label>
      </div>
      <label className="admin-form__field admin-form__field--inline">
        <input
          type="checkbox"
          checked={form.is_visible}
          onChange={(e) => update('is_visible', e.target.checked)}
        />
        <span>Visible on site</span>
      </label>
      <label className="admin-form__field">
        <span>External URL</span>
        <input
          type="text"
          value={form.external_url || ''}
          onChange={(e) => update('external_url', e.target.value)}
        />
      </label>
      <label className="admin-form__field">
        <span>Knowledge Content (for ChromaDB)</span>
        <textarea
          value={form.knowledge_content || ''}
          onChange={(e) => update('knowledge_content', e.target.value)}
          rows={6}
        />
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

// ------------------------------------------------------------------
// KnowledgeSourceForm
// ------------------------------------------------------------------

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
        <span>Source Type *</span>
        <select
          value={form.source_type}
          onChange={(e) => update('source_type', e.target.value as KnowledgeSourceCreate['source_type'])}
        >
          <option value="github_repo">github_repo</option>
          <option value="local_directory">local_directory</option>
          <option value="local_file">local_file</option>
        </select>
      </label>
      <label className="admin-form__field">
        <span>Identifier *</span>
        <input
          type="text"
          value={form.identifier}
          onChange={(e) => update('identifier', e.target.value)}
          required
          placeholder="owner/repo or /path/to/file"
        />
      </label>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Branch (for GitHub)</span>
          <input
            type="text"
            value={form.branch || ''}
            onChange={(e) => update('branch', e.target.value)}
          />
        </label>
        <label className="admin-form__field">
          <span>Base Path</span>
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
        <span>Enabled</span>
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

export function ContentPage() {
  const [activeTab, setActiveTab] = useState<TabId>('cards');

  // Project cards state
  const [cards, setCards] = useState<ProjectCard[]>([]);
  const [cardsLoading, setCardsLoading] = useState(false);
  const [cardsError, setCardsError] = useState('');
  const [editingCard, setEditingCard] = useState<ProjectCard | null>(null);
  const [showCardForm, setShowCardForm] = useState(false);
  const [deleteCardId, setDeleteCardId] = useState<string | null>(null);

  // Sources state
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState('');
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null);
  const [showSourceForm, setShowSourceForm] = useState(false);
  const [deleteSourceId, setDeleteSourceId] = useState<string | null>(null);

  // Sync state
  const [chromaStatus, setChromaStatus] = useState<ChromaStatus | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncJob | null>(null);
  const [syncError, setSyncError] = useState('');

  const loadCards = () => {
    setCardsLoading(true);
    setCardsError('');
    listProjectCards()
      .then((res) => setCards(res.items))
      .catch((err) => setCardsError(err instanceof Error ? err.message : 'Failed to load cards'))
      .finally(() => setCardsLoading(false));
  };

  const loadSources = () => {
    setSourcesLoading(true);
    setSourcesError('');
    listSources()
      .then((res) => setSources(res.items))
      .catch((err) => setSourcesError(err instanceof Error ? err.message : 'Failed to load sources'))
      .finally(() => setSourcesLoading(false));
  };

  const loadChromaStatus = () => {
    getChromaStatus()
      .then(setChromaStatus)
      .catch((err) => setSyncError(err instanceof Error ? err.message : 'Failed to load status'));
  };

  useEffect(() => {
    loadCards();
    loadSources();
    loadChromaStatus();
  }, []);

  const handleCardSubmit = (data: ProjectCardCreate) => {
    const promise = editingCard
      ? updateProjectCard(editingCard.id, data)
      : createProjectCard(data);
    promise
      .then(() => {
        setShowCardForm(false);
        setEditingCard(null);
        loadCards();
      })
      .catch((err) => setCardsError(err instanceof Error ? err.message : 'Failed to save card'));
  };

  const handleCardDelete = () => {
    if (!deleteCardId) return;
    deleteProjectCard(deleteCardId)
      .then(() => {
        setDeleteCardId(null);
        loadCards();
      })
      .catch((err) => setCardsError(err instanceof Error ? err.message : 'Failed to delete card'));
  };

  const handleSourceSubmit = (data: KnowledgeSourceCreate) => {
    const promise = editingSource
      ? updateSource(editingSource.id, data)
      : createSource(data);
    promise
      .then(() => {
        setShowSourceForm(false);
        setEditingSource(null);
        loadSources();
      })
      .catch((err) => setSourcesError(err instanceof Error ? err.message : 'Failed to save source'));
  };

  const handleSourceDelete = () => {
    if (!deleteSourceId) return;
    deleteSource(deleteSourceId)
      .then(() => {
        setDeleteSourceId(null);
        loadSources();
      })
      .catch((err) => setSourcesError(err instanceof Error ? err.message : 'Failed to delete source'));
  };

  const handleSync = () => {
    setSyncLoading(true);
    setSyncError('');
    syncKnowledgeBase()
      .then((res) => {
        setSyncResult(res);
        loadChromaStatus();
      })
      .catch((err) => setSyncError(err instanceof Error ? err.message : 'Sync failed'))
      .finally(() => setSyncLoading(false));
  };

  const cardColumns = [
    { key: 'title', header: 'Title' },
    { key: 'slug', header: 'Slug' },
    {
      key: 'visible',
      header: 'Visible',
      render: (row: ProjectCard) => (row.is_visible ? 'Yes' : 'No'),
    },
    {
      key: 'homepage',
      header: 'Homepage',
      render: (row: ProjectCard) => (row.show_on_homepage > 0 ? row.show_on_homepage : '—'),
    },
    {
      key: 'order',
      header: 'Order',
      render: (row: ProjectCard) => row.display_order,
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (row: ProjectCard) => <TagsList tags={row.tags} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row: ProjectCard) => (
        <div className="admin-row-actions">
          <button
            className="admin-btn admin-btn--small"
            type="button"
            onClick={() => {
              setEditingCard(row);
              setShowCardForm(true);
            }}
          >
            Редактировать
          </button>
          <button
            className="admin-btn admin-btn--small admin-btn--danger"
            type="button"
            onClick={() => setDeleteCardId(row.id)}
          >
            Удалить
          </button>
        </div>
      ),
    },
  ];

  const sourceColumns = [
    { key: 'source_type', header: 'Type' },
    { key: 'identifier', header: 'Identifier' },
    { key: 'branch', header: 'Branch', render: (row: KnowledgeSource) => row.branch || '—' },
    { key: 'base_path', header: 'Path', render: (row: KnowledgeSource) => row.base_path || '—' },
    {
      key: 'enabled',
      header: 'Enabled',
      render: (row: KnowledgeSource) => (row.is_enabled ? 'Yes' : 'No'),
    },
    {
      key: 'last_sync',
      header: 'Last Sync',
      render: (row: KnowledgeSource) => (
        <span className={`admin-sync-status admin-sync-status--${row.last_sync_status}`}>
          {row.last_sync_status}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row: KnowledgeSource) => (
        <div className="admin-row-actions">
          <button
            className="admin-btn admin-btn--small"
            type="button"
            onClick={() => {
              setEditingSource(row);
              setShowSourceForm(true);
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
    <Page title="Content / Knowledge Base">
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

      {activeTab === 'cards' && (
        <div className="admin-tab-panel">
          <Toolbar>
            <button
              className="admin-btn admin-btn--primary"
              type="button"
              onClick={() => {
                setEditingCard(null);
                setShowCardForm(true);
              }}
            >
              + Добавить карточку
            </button>
          </Toolbar>
          {cardsError && <ErrorState message={cardsError} onRetry={loadCards} />}
          {showCardForm && (
            <Card className="admin-form-card">
              <h3>{editingCard ? 'Редактировать карточку' : 'Новая карточка'}</h3>
              <ProjectCardForm
                initial={editingCard || undefined}
                onSubmit={handleCardSubmit}
                onCancel={() => {
                  setShowCardForm(false);
                  setEditingCard(null);
                }}
              />
            </Card>
          )}
          {cardsLoading && <Loading />}
          {!cardsLoading && cards.length === 0 && !cardsError && <EmptyState message="Нет карточек проектов" />}
          {!cardsLoading && cards.length > 0 && !cardsError && (
            <Table columns={cardColumns} rows={cards} keyExtractor={(row) => row.id} />
          )}
          {deleteCardId && (
            <ConfirmDialog
              title="Удалить карточку?"
              message="Это действие нельзя отменить. Карточка исчезнет из публичного сайта."
              onConfirm={handleCardDelete}
              onCancel={() => setDeleteCardId(null)}
            />
          )}
        </div>
      )}

      {activeTab === 'sources' && (
        <div className="admin-tab-panel">
          <Toolbar>
            <button
              className="admin-btn admin-btn--primary"
              type="button"
              onClick={() => {
                setEditingSource(null);
                setShowSourceForm(true);
              }}
            >
              + Добавить источник
            </button>
          </Toolbar>
          {sourcesError && <ErrorState message={sourcesError} onRetry={loadSources} />}
          {showSourceForm && (
            <Card className="admin-form-card">
              <h3>{editingSource ? 'Редактировать источник' : 'Новый источник'}</h3>
              <KnowledgeSourceForm
                initial={editingSource || undefined}
                onSubmit={handleSourceSubmit}
                onCancel={() => {
                  setShowSourceForm(false);
                  setEditingSource(null);
                }}
              />
            </Card>
          )}
          {sourcesLoading && <Loading />}
          {!sourcesLoading && sources.length === 0 && !sourcesError && <EmptyState message="Нет источников знаний" />}
          {!sourcesLoading && sources.length > 0 && !sourcesError && (
            <Table columns={sourceColumns} rows={sources} keyExtractor={(row) => row.id} />
          )}
          {deleteSourceId && (
            <ConfirmDialog
              title="Удалить источник?"
              message="Это действие нельзя отменить."
              onConfirm={handleSourceDelete}
              onCancel={() => setDeleteSourceId(null)}
            />
          )}
        </div>
      )}

      {activeTab === 'sync' && (
        <div className="admin-tab-panel">
          <Card className="dashboard-section">
            <h2 className="dashboard-section__title">ChromaDB Status</h2>
            {chromaStatus?.status === 'ok' && (
              <div className="dashboard-grid dashboard-grid--3">
                <div className="dashboard-metric">
                  <div className="dashboard-metric__label">Status</div>
                  <div className="dashboard-metric__value">OK</div>
                </div>
                <div className="dashboard-metric">
                  <div className="dashboard-metric__label">Collection</div>
                  <div className="dashboard-metric__value">{chromaStatus.collection_name}</div>
                </div>
                <div className="dashboard-metric">
                  <div className="dashboard-metric__label">Chunks</div>
                  <div className="dashboard-metric__value">{chromaStatus.chunks ?? '—'}</div>
                </div>
              </div>
            )}
            {chromaStatus?.status === 'error' && (
              <ErrorState message={chromaStatus.error || 'ChromaDB unavailable'} />
            )}
            {!chromaStatus && <Loading />}
          </Card>

          <Card className="dashboard-section">
            <h2 className="dashboard-section__title">Manual Sync</h2>
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
            {syncError && <ErrorState message={syncError} />}
            {syncResult && (
              <div className="admin-sync-result">
                <p>
                  <strong>Статус:</strong>{' '}
                  <span className={`admin-sync-status admin-sync-status--${syncResult.status}`}>
                    {syncResult.status}
                  </span>
                </p>
                <p>
                  <strong>Documents processed:</strong> {syncResult.stats.documents_processed}
                </p>
                <p>
                  <strong>Chunks created:</strong> {syncResult.stats.chunks_created}
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
        </div>
      )}
    </Page>
  );
}
