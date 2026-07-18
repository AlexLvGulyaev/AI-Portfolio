interface PageProps {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  renderHeader?: (props: { title: React.ReactNode; subtitle?: React.ReactNode }) => React.ReactNode;
  children: React.ReactNode;
}

export function Page({ title, subtitle, action, renderHeader, children }: PageProps) {
  const titleNode = <h1 className="admin-page__title">{title}</h1>;
  const subtitleNode = subtitle ? <p className="admin-page__subtitle">{subtitle}</p> : undefined;

  return (
    <div className="admin-page">
      {renderHeader ? (
        renderHeader({ title: titleNode, subtitle: subtitleNode })
      ) : (
        <div className="admin-page__header">
          <div className="admin-page__titles">
            {titleNode}
            {subtitleNode}
          </div>
          {action && <div className="admin-page__action">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
