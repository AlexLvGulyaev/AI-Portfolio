interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className = '' }: CardProps) {
  return <div className={`admin-card ${className}`.trim()}>{children}</div>;
}
