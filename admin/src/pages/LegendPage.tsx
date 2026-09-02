/**
 * Экран «Обозначения» — обязательный элемент канона APL
 * (admin-console-dual-theme-mirror-inversion): значок → название →
 * расшифровка, сетка 3+3, значок 1.5rem. Каждому чипу/флагу консоли
 * соответствует строка здесь; источник значков — chipContract.
 */
import {
  AUDIT_EVENT_CHIP,
  DOC_INDEX_CHIP,
  FLAG_CHIP,
  MODALITY_CHIP,
  SOURCE_STATUS_CHIP,
  STATUS_CHIP,
  STAGE_CHIP,
  VISIBILITY_CHIP,
  type AiChip,
} from "../utils/chipContract";

const STATUS_DESC: Record<string, string> = {
  success: "Операция или шаг завершились успешно.",
  error: "Ошибка выполнения — шаг или операция не прошли.",
  warning: "Выполнено с предупреждением: результат есть, но требуется внимание.",
  running: "Операция выполняется прямо сейчас.",
  retry: "Выполняется повторная попытка после сбоя.",
  skipped: "Шаг пропущен — выполняться не должен (условие не выполнено).",
  muted: "Статус неизвестен или неприменим.",
};

const MODALITY_DESC: Record<string, string> = {
  text: "Обычный текстовый ответ модели.",
  rag: "Ответ с обращением к базе знаний (retrieval).",
  image: "Генерация или обработка изображений.",
  audio: "Работа с аудио: распознавание и синтез речи.",
  doc: "Работа с документами.",
  log: "Служебные записи без выделенной модальности.",
  mem: "Обращение к памяти диалога.",
  ocr: "Распознавание текста с изображений.",
  vision: "Анализ изображений моделью.",
  test: "Служебные smoke/тестовые вызовы.",
};

const STAGE_DESC: Record<string, string> = {
  success: "Этап конвейера завершён.",
  loading: "Этап запущен, ожидает выполнения.",
  processing: "Этап выполняется.",
  reset: "Этап сброшен или очищен.",
  warning: "Этап завершён с предупреждением.",
  error: "Этап завершился ошибкой.",
  muted: "Состояние этапа неизвестно.",
};

const STAGE_NAMES: Record<string, string> = {
  success: "Успех",
  loading: "Запущено",
  processing: "Выполняется",
  reset: "Сброс",
  warning: "Предупреждение",
  error: "Ошибка",
  muted: "Нет данных",
};

const SOURCE_STATUS_DESC: Record<string, string> = {
  approved: "Источник одобрен и включён в состав KB.",
  need_preview: "Требуется preview перед одобрением.",
  preview_ready: "Preview построен — можно одобрять.",
  patterns_changed: "В источнике есть изменения — нужен пересмотр.",
  error: "Ошибка обработки источника.",
};

const DOC_INDEX_DESC: Record<string, string> = {
  indexed: "Документ есть в векторном индексе (есть чанки).",
  not_indexed: "Документа нет в индексе (чанков нет).",
  unknown: "Счётчик чанков недоступен.",
};

const FLAG_DESC: Record<string, string> = {
  active: "Флаг активности (провайдер, промпт, бэкенд, диалог).",
  inactive: "Неактивен: сессия завершена или объект отключён от активности.",
  fallback: "Резервный провайдер — используется при сбое основного.",
  off: "Выключен вручную.",
  builtin: "Вшитый (builtin): поставляется с системой, не создан вручную.",
  ready: "Готов к работе, проверка пройдена.",
  down: "Недоступен или ошибка проверки.",
  flag_unknown: "Состояние неизвестно.",
  empty: "Пусто: записей нет.",
  normal: "Норма — все проверки пройдены.",
  degraded: "Деградация: работает с ограничениями.",
  pending: "Ожидание: ещё не подтверждено.",
};

const AUDIT_EVENT_DESC: Record<string, string> = {
  admin_login: "Вход в админ-консоль.",
  admin_action: "Действие в админ-консоли.",
  site_visit: "Посещение публичного сайта.",
  chat_request: "Запрос чата на витрине.",
  rag_query: "RAG-запрос к базе знаний.",
  provider_switch: "Переключение LLM-провайдера.",
};

const VISIBILITY_DESC: Record<string, string> = {
  visible: "Карточка видна на публичном сайте.",
  hidden: "Карточка скрыта с публичного сайта.",
};

type LegendRow = { emoji: string; name: string; desc: string };

function LegendSection({ title, rows }: { title: string; rows: LegendRow[] }) {
  return (
    <div className="legend-section">
      <h2 className="card__title">{title}</h2>
      <div className="legend-grid">
        {rows.map((r) => (
          <div className="legend-item" key={r.name}>
            <span className="legend-item__icon ai-status--icon-lg" aria-hidden="true">
              {r.emoji}
            </span>
            <span className="legend-item__name">{r.name}</span>
            <span className="legend-item__desc">{r.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function chipRows(chip: Record<string, AiChip>, desc: Record<string, string>): LegendRow[] {
  return Object.entries(chip).map(([key, c]) => ({
    emoji: c.emoji,
    name: c.label,
    desc: desc[key] ?? "",
  }));
}

export function LegendPage() {
  return (
    <div className="page page--legend">
      <div className="card" style={{ padding: "20px 24px" }}>
        <h1 className="page-title">Обозначения</h1>
        <p className="muted" style={{ fontSize: "0.875rem" }}>
          Значки статус-чипов, модальностей, флагов и этапов конвейера во всех
          разделах консоли. Один значок — одно понятие; при наведении на значок
          в списках всплывает комментарий «Тип: Значение».
        </p>

        <LegendSection title="Статусы операций" rows={chipRows(STATUS_CHIP, STATUS_DESC)} />

        <LegendSection title="Статусы источников" rows={chipRows(SOURCE_STATUS_CHIP, SOURCE_STATUS_DESC)} />

        <LegendSection title="Индексация документов" rows={chipRows(DOC_INDEX_CHIP, DOC_INDEX_DESC)} />

        <LegendSection title="Флаги готовности" rows={chipRows(FLAG_CHIP, FLAG_DESC)} />

        <LegendSection title="Типы событий" rows={chipRows(AUDIT_EVENT_CHIP, AUDIT_EVENT_DESC)} />

        <LegendSection title="Модальности" rows={chipRows(MODALITY_CHIP, MODALITY_DESC)} />

        <LegendSection
          title="Этапы конвейера"
          rows={Object.entries(STAGE_CHIP).map(([key, emoji]) => ({
            emoji,
            name: STAGE_NAMES[key] ?? key,
            desc: STAGE_DESC[key] ?? "",
          }))}
        />

        <LegendSection title="Видимость карточек" rows={chipRows(VISIBILITY_CHIP, VISIBILITY_DESC)} />
      </div>
    </div>
  );
}