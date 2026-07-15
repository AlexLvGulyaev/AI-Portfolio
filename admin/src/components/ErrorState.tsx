interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="admin-error">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry} type="button">
          Повторить
        </button>
      )}
    </div>
  );
}
