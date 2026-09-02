import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { useTheme } from '../hooks/useTheme';

type NavItem =
  | { type: 'link'; path: string; label: string; icon: string }
  | { type: 'group'; label: string; children: { path: string; label: string; icon: string }[] };

// Эмодзи-иконки пунктов — канон AIC (Sidebar.jsx): прямые аналоги пунктов
// AIC берут ту же иконку (Обзор=📊 «Панель состояния», Retrieval=🧭
// «Оркестратор», Документы=📚 «База знаний», Логи 📜, Диалоги 💬,
// Аудит 📋, Выйти 🚪). Разделы — меню-канон APL
// (shared/patterns/admin-menu-canon.md): Система → База знаний →
// Аналитика → Наблюдаемость.
const navItems: NavItem[] = [
  {
    type: 'group',
    label: 'Система',
    children: [
      { path: '/system', label: 'Обзор', icon: '📊' },
      { path: '/system/retrieval', label: 'Retrieval', icon: '🧭' },
      { path: '/system/ai', label: 'AI-настройки', icon: '⚙️' },
    ],
  },
  {
    type: 'group',
    label: 'База знаний',
    children: [
      { path: '/content/cards', label: 'Карточки проектов', icon: '🗂️' },
      { path: '/content/sources', label: 'Источники и синхронизация', icon: '🔄' },
      { path: '/content/documents', label: 'Документы', icon: '📚' },
    ],
  },
  {
    type: 'group',
    label: 'Аналитика',
    children: [
      { path: '/analytics/presale', label: 'Пресейл', icon: '📈' },
    ],
  },
  {
    type: 'group',
    label: 'Наблюдаемость',
    children: [
      { path: '/logs', label: 'Логи', icon: '📜' },
      { path: '/conversations', label: 'Диалоги', icon: '💬' },
      { path: '/audit', label: 'Аудит', icon: '📋' },
    ],
  },
  {
    // Канон меню APL: замыкающая группа «Справка» — экран «Обозначения».
    type: 'group',
    label: 'Справка',
    children: [
      { path: '/help/legend', label: 'Обозначения', icon: '🔣' },
    ],
  },
];

function isGroupActive(children: { path: string }[], pathname: string): boolean {
  return children.some((child) => pathname.startsWith(child.path));
}

export function AdminLayout() {
  const { logout } = useAuth();
  const { toggleTheme, toggleLabel } = useTheme();
  const { pathname } = useLocation();

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <div className="admin-sidebar__brand">
          {/* Бренд-марка APL — как в презентациях (apl-brand-lockup,
              круг #7C3AED с белой надписью APL, AIP Dark Visual Language:
              purple = бренд). */}
          <span className="apl-brand-mark" aria-label="APL">APL</span>
          <span>AI Portfolio</span>
        </div>
        <nav className="admin-nav">
          {navItems.map((item) =>
            item.type === 'link' ? (
              <NavLink
                key={item.path}
                to={item.path}
                // /system не должен подсвечиваться на вложенных путях
                // (например, /system/retrieval) — только на самом /system.
                end={item.path === '/system'}
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
                      end
                      // end: «Обзор» (/system) не должен подсвечиваться на
                      // вложенных путях типа /system/retrieval и /system/ai.
                      className={({ isActive }) =>
                        `admin-nav__link admin-nav__link--child${isActive ? ' admin-nav__link--active' : ''}`
                      }
                    >
                      <span className="admin-nav__icon" aria-hidden="true">{child.icon}</span>
                      <span>{child.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          )}
        </nav>
        <div className="admin-sidebar__footer">
          {/* Переключатель темы — канон: в футере сайдбара, над «Выход»;
              подпись показывает тему, в которую переключаемся. */}
          <button className="admin-sidebar__logout" onClick={toggleTheme} type="button">
            <span className="admin-nav__icon" aria-hidden="true">
              {toggleLabel.split(' ')[0]}
            </span>
            <span>{toggleLabel.split(' ').slice(1).join(' ')}</span>
          </button>
          <button className="admin-sidebar__logout" onClick={logout} type="button">
            <span className="admin-nav__icon" aria-hidden="true">🚪</span>
            <span>Выход</span>
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
