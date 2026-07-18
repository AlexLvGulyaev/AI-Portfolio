import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

type NavItem =
  | { type: 'link'; path: string; label: string }
  | { type: 'group'; label: string; children: { path: string; label: string }[] };

const navItems: NavItem[] = [
  { type: 'link', path: '/system', label: 'Системные настройки' },
  {
    type: 'group',
    label: 'Контент/база знаний',
    children: [
      { path: '/content/cards', label: 'Карточки проектов' },
      { path: '/content/sources', label: 'Источники знаний' },
      { path: '/content/sync', label: 'Синхронизация' },
    ],
  },
  { type: 'link', path: '/logs', label: 'Логи' },
  { type: 'link', path: '/conversations', label: 'Диалоги' },
];

function isGroupActive(children: { path: string }[], pathname: string): boolean {
  return children.some((child) => pathname.startsWith(child.path));
}

export function AdminLayout() {
  const { logout } = useAuth();
  const { pathname } = useLocation();

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="admin-sidebar__brand">AI Portfolio</div>
        <nav className="admin-nav">
          {navItems.map((item) =>
            item.type === 'link' ? (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `admin-nav__link${isActive ? ' admin-nav__link--active' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ) : (
              <div
                key={item.label}
                className={`admin-nav__group${isGroupActive(item.children, pathname) ? ' admin-nav__group--active' : ''}`}
              >
                <div className="admin-nav__group-label">{item.label}</div>
                <div className="admin-nav__group-children">
                  {item.children.map((child) => (
                    <NavLink
                      key={child.path}
                      to={child.path}
                      className={({ isActive }) =>
                        `admin-nav__link admin-nav__link--child${isActive ? ' admin-nav__link--active' : ''}`
                      }
                    >
                      {child.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          )}
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
