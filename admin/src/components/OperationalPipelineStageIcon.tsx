import type { AfPipelineStageVariant } from "../utils/operationalConsoleUi";
import { STAGE_CHIP } from "../utils/chipContract";

type Props = {
  variant: AfPipelineStageVariant;
  className?: string;
};

/**
 * Значок этапа конвейера — канон APL §3: значки без слов
 * (✔︎ успех · 🔄 в работе · ❌ ошибка · ⚠️ предупреждение ·
 * ↺ сброс · ➖ нет данных). Эмодзи из chipContract — единственного
 * источника значков консоли.
 */
export function OperationalPipelineStageIcon({ variant, className = "" }: Props) {
  return (
    <span
      className={`af-pipeline-stage-icon af-pipeline-stage-icon--${variant}${
        className ? ` ${className}` : ""
      }`}
      aria-hidden
    >
      {STAGE_CHIP[variant]}
    </span>
  );
}