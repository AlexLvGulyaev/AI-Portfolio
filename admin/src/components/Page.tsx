interface PageProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}

export function Page({ title, subtitle, action, children }: PageProps) {
  return (
    <div className="admin-page">
      <div className="admin-page__header">
        <div className="admin-page__titles">
          <h1 className="admin-page__title">{title}</h1>
          {subtitle && <p className="admin-page__subtitle">{subtitle}</p>}
        </div>
        {action && <div className="admin-page__action">{action}</div>}
      </div>
      {children}
    </div>
  );
}
