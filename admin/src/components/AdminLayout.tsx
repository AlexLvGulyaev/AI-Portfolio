import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

const navItems = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/content', label: 'Content / Knowledge Base' },
  { path: '/logs', label: 'Logs / Conversations' },
];

export function AdminLayout() {
  const { logout } = useAuth();

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="admin-sidebar__brand">AI Portfolio</div>
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
        <div className="admin-sidebar__footer">
          <button className="admin-sidebar__logout" onClick={logout} type="button">
            Выход
          </button>
        </div>
      </aside>

      <div className="admin-main">
        <div className="admin-header__wrapper">
          <header className="admin-header">
            <div className="admin-header__title">Admin Console</div>
            <div className="admin-header__brand">Zerocoder</div>
          </header>
          <div className="admin-header__subtitle">
            FastAPI · консоль наблюдаемости · auth token
          </div>
        </div>
        <main className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
