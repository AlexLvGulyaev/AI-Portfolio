interface EmptyStateProps {
  message?: string;
}

export function EmptyState({ message = 'Нет данных' }: EmptyStateProps) {
  return <div className="admin-empty">{message}</div>;
}
