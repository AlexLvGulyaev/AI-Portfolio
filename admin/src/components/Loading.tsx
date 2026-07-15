export function Loading({ message = 'Загрузка...' }: { message?: string }) {
  return <div className="admin-loading">{message}</div>;
}
