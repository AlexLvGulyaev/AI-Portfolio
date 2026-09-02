/**
 * Значок-флаг (эмодзи-контракт APL, правило 7): заменяет текстовый
 * флаг в списке/таймлайне; при наведении всплывает «Тип: Значение».
 * Значок наследует размер строки; каждый значок имеет строку
 * в легенде «Обозначения».
 */
import type { AiChip } from "../utils/chipContract";
import { flagTitle } from "../utils/chipContract";

type Props = {
  chip: AiChip;
  /** Тип из тултипа («Статус», «Индексация», …) — sentence case. */
  type: string;
  className?: string;
};

export function FlagIcon({ chip, type, className = "" }: Props) {
  return (
    <span
      className={`flag-icon${className ? ` ${className}` : ""}`}
      title={flagTitle(type, chip.label)}
      aria-label={flagTitle(type, chip.label)}
    >
      <span aria-hidden="true">{chip.emoji}</span>
    </span>
  );
}