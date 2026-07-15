interface ConfirmDialogProps {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
}

export function ConfirmDialog({
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = 'Удалить',
  cancelText = 'Отмена',
}: ConfirmDialogProps) {
  return (
    <div className="admin-dialog-overlay">
      <div className="admin-dialog">
        <h3 className="admin-dialog__title">{title}</h3>
        <p className="admin-dialog__message">{message}</p>
        <div className="admin-dialog__actions">
          <button className="admin-btn admin-btn--secondary" onClick={onCancel} type="button">
            {cancelText}
          </button>
          <button className="admin-btn admin-btn--danger" onClick={onConfirm} type="button">
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
