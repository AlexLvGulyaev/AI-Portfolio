interface PageProps {
  title: string;
  children: React.ReactNode;
}

export function Page({ title, children }: PageProps) {
  return (
    <div className="admin-page">
      <h1 className="admin-page__title">{title}</h1>
      {children}
    </div>
  );
}
