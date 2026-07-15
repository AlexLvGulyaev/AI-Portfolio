interface ToolbarProps {
  children: React.ReactNode;
}

export function Toolbar({ children }: ToolbarProps) {
  return <div className="admin-toolbar">{children}</div>;
}
