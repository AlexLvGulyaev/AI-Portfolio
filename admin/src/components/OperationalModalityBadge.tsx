import {
  OPERATIONAL_MODALITY_LABEL,
  normalizeOperationalModality,
  operationalModalityBadgeClassList,
  type OperationalModality,
} from "../utils/operationalConsoleUi";
import { MODALITY_CHIP } from "../utils/chipContract";

type Props = {
  modality: OperationalModality | string;
  className?: string;
  title?: string;
};

export function OperationalModalityBadge({ modality, className = "", title }: Props) {
  const safe =
    typeof modality === "string" ? normalizeOperationalModality(modality) : modality;
  const label = OPERATIONAL_MODALITY_LABEL[safe];
  const emoji = MODALITY_CHIP[safe]?.emoji ?? "";
  return (
    <span
      className={`${operationalModalityBadgeClassList(safe)}${className ? ` ${className}` : ""}`}
      title={title ?? label}
    >
      {emoji ? <span aria-hidden="true">{emoji}</span> : null}
      <span>{label}</span>
    </span>
  );
}