import { useEffect, useMemo, useState } from 'react';
import { Page } from '../components/Page';
import { Loading } from '../components/Loading';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { Modal } from '../components/Modal';
import { ConfirmDialog } from '../components/ConfirmDialog';
import {
  listProjectCards,
  createProjectCard,
  updateProjectCard,
  deleteProjectCard,
  getProjectCardChunks,
  type ProjectCard,
  type ProjectCardCreate,
  type KnowledgeChunk,
} from '../api/client';

const PAGE_SIZE = 10;

type VisibilityFilter = 'all' | 'visible' | 'hidden';
type HomepageFilter = 'all' | 'homepage' | 'no';

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU');
}

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
          <span>Название *</span>
          <input
            type="text"
            value={form.title}
            onChange={(e) => update('title', e.target.value)}
            required
          />
        </label>
      </div>
      <label className="admin-form__field">
        <span>Краткое описание *</span>
        <textarea
          value={form.short_description}
          onChange={(e) => update('short_description', e.target.value)}
          rows={3}
          required
        />
      </label>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Категория</span>
          <input
            type="text"
            value={form.category}
            onChange={(e) => update('category', e.target.value)}
          />
        </label>
        <label className="admin-form__field">
          <span>Теги (через запятую)</span>
          <input
            type="text"
            value={Array.isArray(form.tags) ? form.tags.join(', ') : form.tags}
            onChange={(e) => update('tags', e.target.value.split(',').map((t) => t.trim()).filter(Boolean) as never)}
          />
        </label>
      </div>
      <div className="admin-form__grid">
        <label className="admin-form__field">
          <span>Порядок отображения</span>
          <input
            type="number"
            value={form.display_order}
            onChange={(e) => update('display_order', Number(e.target.value))}
          />
        </label>
        <label className="admin-form__field">
          <span>На главной (0..4)</span>
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
        <span>Видна на сайте</span>
      </label>
      <label className="admin-form__field">
        <span>Внешний URL</span>
        <input
          type="text"
          value={form.external_url || ''}
          onChange={(e) => update('external_url', e.target.value)}
        />
      </label>
      <label className="admin-form__field">
        <span>Содержимое базы знаний (для ChromaDB)</span>
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
// Macro panels
// ------------------------------------------------------------------

function Panel({ title, children, wide = false }: { title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={`op-panel${wide ? ' op-panel--wide' : ''}`}>
      <h3 className="op-panel__title">{title}</h3>
      <div className="op-panel__body">{children}</div>
    </div>
  );
}

function MetadataRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="op-meta-row">
      <span className="op-meta-row__label">{label}</span>
      <span className="op-meta-row__value">{value}</span>
    </div>
  );
}

function PassportPanel({ card }: { card: ProjectCard }) {
  return (
    <Panel title="Паспорт">
      <MetadataRow label="Название" value={card.title} />
      <MetadataRow label="Slug" value={card.slug} />
      <MetadataRow label="Категория" value={card.category} />
      <MetadataRow label="Теги" value={<TagsList tags={card.tags} />} />
      <MetadataRow label="Создана" value={formatDate(card.created_at)} />
    </Panel>
  );
}

function OperationPanel({ card }: { card: ProjectCard }) {
  return (
    <Panel title="Эксплуатация">
      <MetadataRow label="Внешний URL" value={card.external_url || '—'} />
      <MetadataRow label="Видимость" value={card.is_visible ? 'Видна на сайте' : 'Скрыта'} />
      <MetadataRow label="На главной" value={card.show_on_homepage > 0 ? `позиция ${card.show_on_homepage}` : 'нет'} />
      <MetadataRow label="Порядок" value={card.display_order} />
      <MetadataRow label="Изменена" value={formatDate(card.updated_at)} />
    </Panel>
  );
}

function DescriptionPanel({ card }: { card: ProjectCard }) {
  return (
    <Panel title="Описание" wide>
      <p className="op-text">{card.short_description}</p>
    </Panel>
  );
}

function KnowledgePanel({ chunks, loading, error }: { chunks: KnowledgeChunk[]; loading: boolean; error: string }) {
  return (
    <Panel title="База знаний" wide>
      {loading && <Loading />}
      {error && <ErrorState message={error} />}
      {!loading && !error && chunks.length === 0 && <EmptyState message="Нет чанков в ChromaDB для этого проекта" />}
      {!loading && !error && chunks.length > 0 && (
        <ul className="op-chunk-list">
          {chunks.map((chunk, idx) => (
            <li key={chunk.id || idx} className="op-chunk">
              <div className="op-chunk__index">Чанк {idx + 1}</div>
              <div className="op-chunk__text">{chunk.content}</div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------
// Main page
// ------------------------------------------------------------------

export function ProjectCardsPage() {
  const [cards, setCards] = useState<ProjectCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null);
  const [deleteCardId, setDeleteCardId] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>('all');
  const [homepageFilter, setHomepageFilter] = useState<HomepageFilter>('all');
  const [offset, setOffset] = useState(0);

  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunksError, setChunksError] = useState('');

  const load = () => {
    setLoading(true);
    setError('');
    listProjectCards()
      .then((res) => {
        setCards(res.items);
        if (!selectedId && res.items.length > 0) {
          setSelectedId(res.items[0].id);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось загрузить карточки'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(() => {
    const set = new Set(cards.map((c) => c.category));
    return Array.from(set).sort();
  }, [cards]);

  const filteredCards = useMemo(() => {
    const needle = search.toLowerCase().trim();
    return cards.filter((card) => {
      if (needle) {
        const hay = `${card.title} ${card.slug} ${card.tags.join(' ')}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      if (categoryFilter && card.category !== categoryFilter) return false;
      if (visibilityFilter === 'visible' && !card.is_visible) return false;
      if (visibilityFilter === 'hidden' && card.is_visible) return false;
      if (homepageFilter === 'homepage' && card.show_on_homepage === 0) return false;
      if (homepageFilter === 'no' && card.show_on_homepage > 0) return false;
      return true;
    });
  }, [cards, search, categoryFilter, visibilityFilter, homepageFilter]);

  const paginatedCards = useMemo(() => {
    return filteredCards.slice(offset, offset + PAGE_SIZE);
  }, [filteredCards, offset]);

  const totalPages = Math.ceil(filteredCards.length / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  useEffect(() => {
    setOffset(0);
  }, [search, categoryFilter, visibilityFilter, homepageFilter]);

  const selectedIndex = useMemo(() => paginatedCards.findIndex((c) => c.id === selectedId), [paginatedCards, selectedId]);
  const selected = useMemo(() => paginatedCards[selectedIndex] || null, [paginatedCards, selectedIndex]);

  useEffect(() => {
    if (!selected) {
      setChunks([]);
      return;
    }
    setChunksLoading(true);
    setChunksError('');
    getProjectCardChunks(selected.id)
      .then((res) => setChunks(res.items))
      .catch((err) => setChunksError(err instanceof Error ? err.message : 'Не удалось загрузить чанки'))
      .finally(() => setChunksLoading(false));
  }, [selected]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!paginatedCards.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = selectedIndex + 1;
        if (next < paginatedCards.length) {
          setSelectedId(paginatedCards[next].id);
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = selectedIndex - 1;
        if (prev >= 0) {
          setSelectedId(paginatedCards[prev].id);
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [paginatedCards, selectedIndex]);

  const handleSubmit = (data: ProjectCardCreate) => {
    const promise = modalMode === 'edit' && selected
      ? updateProjectCard(selected.id, data)
      : createProjectCard(data);
    promise
      .then(() => {
        setModalMode(null);
        load();
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось сохранить карточку'));
  };

  const handleDelete = () => {
    if (!deleteCardId) return;
    deleteProjectCard(deleteCardId)
      .then(() => {
        setDeleteCardId(null);
        if (selectedId === deleteCardId) setSelectedId(null);
        load();
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Не удалось удалить карточку'));
  };

  return (
    <Page
      title="Карточки проектов"
      renderHeader={({ title }) => (
        <div className="admin-page__header project-cards-header">
          {title}
          {selected && (
            <div className="project-cards-header__actions">
              <button
                className="admin-btn admin-btn--primary"
                type="button"
                onClick={() => setModalMode('create')}
              >
                + Добавить
              </button>
              <button
                className="admin-btn"
                type="button"
                onClick={() => setModalMode('edit')}
              >
                Редактировать
              </button>
              <button
                className="admin-btn admin-btn--danger"
                type="button"
                onClick={() => setDeleteCardId(selected.id)}
              >
                Удалить
              </button>
              <button
                className="admin-btn"
                type="button"
                onClick={load}
                disabled={loading}
              >
                Обновить
              </button>
            </div>
          )}
        </div>
      )}
    >
      <div className="project-cards-workspace">
        <div className="project-cards-list">
          <div className="project-cards-filters">
            <label className="admin-form__field project-cards-filters__search">
              <span>Поиск</span>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="название, slug, тег…"
              />
            </label>
            <label className="admin-form__field">
              <span>Категория</span>
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                <option value="">Все</option>
                {categories.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </label>
            <label className="admin-form__field">
              <span>Видимость</span>
              <select value={visibilityFilter} onChange={(e) => setVisibilityFilter(e.target.value as VisibilityFilter)}>
                <option value="all">Все</option>
                <option value="visible">Видимые</option>
                <option value="hidden">Скрытые</option>
              </select>
            </label>
            <label className="admin-form__field">
              <span>Главная</span>
              <select value={homepageFilter} onChange={(e) => setHomepageFilter(e.target.value as HomepageFilter)}>
                <option value="all">Все</option>
                <option value="homepage">На главной</option>
                <option value="no">Не на главной</option>
              </select>
            </label>
          </div>

          <div className="project-cards-counter">
            Стр. {currentPage} из {totalPages || 1} · всего: {filteredCards.length}
          </div>

          {error && <ErrorState message={error} onRetry={load} />}
          {loading && <Loading />}
          {!loading && filteredCards.length === 0 && !error && <EmptyState message="Нет карточек проектов" />}
          {!loading && filteredCards.length > 0 && !error && (
            <ul className="project-cards-items">
              {paginatedCards.map((card) => (
                <li
                  key={card.id}
                  className={`project-cards-item${selectedId === card.id ? ' project-cards-item--active' : ''}`}
                  onClick={() => setSelectedId(card.id)}
                >
                  <div className="project-cards-item__top">
                    <span className="project-cards-item__date">
                      {card.created_at ? new Date(card.created_at).toLocaleDateString('ru-RU') : '—'}
                    </span>
                    <div className="project-cards-item__tags-inline">
                      <TagsList tags={card.tags} />
                    </div>
                    <span className={`project-cards-item__status${card.is_visible ? '' : ' project-cards-item__status--inactive'}`}>
                      {card.is_visible ? 'ВИДНА' : 'СКРЫТА'}
                    </span>
                  </div>
                  <div className="project-cards-item__title">{card.title}</div>
                  <div className="project-cards-item__meta">
                    {card.category} • {card.show_on_homepage > 0 ? `главная ${card.show_on_homepage}` : 'не на главной'} • порядок {card.display_order}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {totalPages > 1 && (
            <div className="admin-pagination">
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              >
                ← Назад
              </button>
              <span className="admin-pagination__info">
                Страница {currentPage} из {totalPages}
              </span>
              <button
                className="admin-btn admin-btn--small"
                type="button"
                disabled={offset + PAGE_SIZE >= filteredCards.length}
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
              >
                Вперёд →
              </button>
            </div>
          )}
        </div>

        <div className="project-cards-right">
          <div className="project-cards-detail">
            {!selected ? (
              <EmptyState message="Выберите карточку проекта из списка" />
            ) : (
              <>
                <div className="project-cards-detail__header">
                  <h2 className="project-cards-detail__title">{selected.title}</h2>
                  <span className={`project-cards-detail__status${selected.is_visible ? '' : ' project-cards-detail__status--inactive'}`}>
                    {selected.is_visible ? 'ВИДНА' : 'СКРЫТА'}
                  </span>
                </div>
                <div className="project-cards-panels">
                  <PassportPanel card={selected} />
                  <OperationPanel card={selected} />
                  <DescriptionPanel card={selected} />
                  <KnowledgePanel chunks={chunks} loading={chunksLoading} error={chunksError} />
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {modalMode && (
        <Modal
          title={modalMode === 'create' ? 'Новая карточка проекта' : 'Редактировать карточку'}
          onClose={() => setModalMode(null)}
        >
          <ProjectCardForm
            initial={modalMode === 'edit' ? selected || undefined : undefined}
            onSubmit={handleSubmit}
            onCancel={() => setModalMode(null)}
          />
        </Modal>
      )}

      {deleteCardId && (
        <ConfirmDialog
          title="Удалить карточку?"
          message="Это действие нельзя отменить. Карточка исчезнет из публичного сайта."
          onConfirm={handleDelete}
          onCancel={() => setDeleteCardId(null)}
        />
      )}
    </Page>
  );
}
