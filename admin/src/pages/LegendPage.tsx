/**
 * Экран «Обозначения» — обязательный элемент канона APL
 * (admin-console-dual-theme-mirror-inversion): значок → название →
 * расшифровка, сетка 3+3, значок 1.5rem. Каждому чипу консоли
 * соответствует строка здесь; источник значков — chipContract.
 */
import { MODALITY_CHIP, STATUS_CHIP, STAGE_CHIP, type AiChip } from "../utils/chipContract";

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
    <div className="page">
      <div className="card" style={{ padding: "20px 24px" }}>
        <h1 className="page-title">Обозначения</h1>
        <p className="muted" style={{ fontSize: "0.875rem" }}>
          Значки статус-чипов, модальностей и этапов конвейера во всех разделах
          консоли. Один значок — одно понятие.
        </p>

        <LegendSection title="Статусы" rows={chipRows(STATUS_CHIP, STATUS_DESC)} />

        <LegendSection title="Модальности" rows={chipRows(MODALITY_CHIP, MODALITY_DESC)} />

        <LegendSection
          title="Этапы конвейера"
          rows={Object.entries(STAGE_CHIP).map(([key, emoji]) => ({
            emoji,
            name: STAGE_NAMES[key] ?? key,
            desc: STAGE_DESC[key] ?? "",
          }))}
        />
      </div>
    </div>
  );
}