/**
 * Канонный статус-чип (эмодзи-контракт APL).
 * Чип = эмодзи + подпись; прозрачный фон; наследует размер строки
 * («одна строка — один размер»); sentence case. Эмодзи заменяет
 * точку-индикатор канона.
 */
import { STATUS_CHIP, statusChipKey, type AiStatusKey } from "../utils/chipContract";

type Props = {
  /** Машинный статус (success/error/failed/…) — нормализуется контрактом. */
  status: string | null | undefined;
  /** Переопределить подпись (по умолчанию — канонная подпись ключа). */
  label?: string;
  className?: string;
};

export function StatusChip({ status, label, className = "" }: Props) {
  const key: AiStatusKey = statusChipKey(status);
  const chip = STATUS_CHIP[key];
  return (
    <span
      className={`ai-status ai-status--emoji ai-status--${key}${
        className ? ` ${className}` : ""
      }`}
      title={label ?? chip.label}
    >
      <span aria-hidden="true">{chip.emoji}</span>
      <span>{label ?? chip.label}</span>
    </span>
  );
}