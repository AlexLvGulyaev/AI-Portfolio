export function OperationalRefreshButton({
  loading,
  onClick,
  className,
}: {
  loading?: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={["ops-refresh-btn", className].filter(Boolean).join(" ")}
      onClick={onClick}
      disabled={!!loading}
      aria-busy={loading || undefined}
    >
      {loading ? "Обновление…" : "Обновить"}
    </button>
  );
}
