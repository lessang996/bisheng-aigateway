import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { toggleSidebar, type RootState } from '../store';

const items = [
  ['/dashboard', '工作台', '▦'],
  ['/agents', 'Agent 管理', '◇'],
  ['/conversations', '对话中心', '◌'],
  ['/reports', '报告中心', '▤'],
  ['/knowledge', '知识库', '▱'],
  ['/users', '用户与权限', '♙'],
  ['/system/health', '系统监控', '◉'],
];

export default function BasicLayout({ children }: { children: ReactNode }) {
  const collapsed = useSelector((state: RootState) => state.ui.sidebarCollapsed);
  const dispatch = useDispatch();
  const location = useLocation();

  // 根据当前路径动态设置标题
  const title = location.pathname.startsWith('/reports')
    ? '报告中心'
    : location.pathname === '/dashboard'
    ? '工作台'
    : '系统管理';

  return (
    <div className={`gateway-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">B</span>
          <span className="brand-name">
            BiSheng <b>Gateway</b>
          </span>
        </div>
        <nav aria-label="主导航">
          <div className="nav-label">工作空间</div>
          {items.map(([path, label, icon]) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{icon}</span>
              <span>{label}</span>
              {path === '/agents' && <i className="nav-count">3</i>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="environment">
            <span className="status-dot online" />
            生产环境
          </div>
          <small>v1.0.0 · Gateway API 正常</small>
        </div>
      </aside>

      <section className="app-frame">
        <header className="topbar">
          <button
            className="icon-button"
            aria-label="折叠导航"
            onClick={() => dispatch(toggleSidebar())}
          >
            ☰
          </button>
          <div className="breadcrumb">
            AI Gateway <span>/</span> {title}
          </div>
          <div className="topbar-actions">
            <button className="search-button">
              ⌕ <span>搜索 Agent、报告或会话</span>
              <kbd>⌘ K</kbd>
            </button>
            <button className="icon-button" aria-label="通知">
              ♧<i className="notification-dot" />
            </button>
            <div className="user-avatar">Z</div>
            <div className="user-meta">
              <b>cqbank</b>
              <small>系统管理员</small>
            </div>
          </div>
        </header>
        <main className="content">{children}</main>
      </section>
    </div>
  );
}