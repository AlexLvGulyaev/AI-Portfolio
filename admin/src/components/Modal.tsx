interface ModalProps {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  actions?: React.ReactNode;
}

export function Modal({ title, children, onClose, actions }: ModalProps) {
  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
        <div className="admin-modal__header">
          <h3 className="admin-modal__title">{title}</h3>
          <button className="admin-modal__close" onClick={onClose} type="button" aria-label="Закрыть">
            ×
          </button>
        </div>
        <div className="admin-modal__body">{children}</div>
        {actions && <div className="admin-modal__actions">{actions}</div>}
      </div>
    </div>
  );
}
