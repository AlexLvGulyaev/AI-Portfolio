import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { Card } from './Card';

const navItems = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/content', label: 'Content / Knowledge Base' },
  { path: '/logs', label: 'Logs / Conversations' },
];

export function AdminLayout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <div className="admin-header__brand">AI Portfolio Admin</div>
        <button className="admin-header__logout" onClick={handleLogout} type="button">
          Выйти
        </button>
      </header>
      <div className="admin-body">
        <aside className="admin-sidebar">
          <nav className="admin-nav">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `admin-nav__link${isActive ? ' admin-nav__link--active' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="admin-content">
          <Card>
            <Outlet />
          </Card>
        </main>
      </div>
    </div>
  );
}
