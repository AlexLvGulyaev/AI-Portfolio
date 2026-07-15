interface TableColumn<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
}

interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  keyExtractor: (row: T) => string;
}

export function Table<T>({ columns, rows, keyExtractor }: TableProps<T>) {
  return (
    <table className="admin-table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key} className="admin-table__header">
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={keyExtractor(row)} className="admin-table__row">
            {columns.map((column) => (
              <td key={`${keyExtractor(row)}-${column.key}`} className="admin-table__cell">
                {column.render ? column.render(row) : String((row as Record<string, unknown>)[column.key] ?? '')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
