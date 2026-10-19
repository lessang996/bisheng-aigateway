
import type { ReactNode } from 'react';

import { NavLink, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';

import { useAccess, type MenuItem } from '../access';
import { toggleSidebar, type RootState } from '../store';

export default function BasicLayout({
  children,
}: {
  children: ReactNode;
}) {
  const identity = useAccess();
  const dispatch = useDispatch();
  const location = useLocation();

  // 获取侧边栏折叠状态
  const collapsed = useSelector(
    (state: RootState) => state.ui.sidebarCollapsed,
  );

  // 根据当前路径动态设置标题
  const title =
    [...identity.menus]
      .sort(
        (a, b) =>
          (b.path?.length ?? 0) - (a.path?.length ?? 0),
      )
      .find(
        (item) =>
          item.path === location.pathname ||
          (
            item.path != null &&
            location.pathname.startsWith(item.path + '/')
          ),
      )?.name ?? '系统管理';

  /**
   * 递归渲染菜单树
   *
   * directory：目录节点
   * external：外部链接
   * page：内部页面
   */
  const renderMenus = (
    parent: number | null = null,
  ): ReactNode =>
    identity.menus
      .filter((item) => item.parent_id === parent)
      .map((item: MenuItem) => {
        // 目录菜单
        if (item.kind === 'directory') {
          return (
            <div key={item.id}>
              <div className="nav-label">
                {item.name}
              </div>

              {renderMenus(item.id)}
            </div>
          );
        }

        // 外部链接
        if (item.kind === 'external') {
          return (
            <a
              key={item.id}
              className="nav-item"
              href={item.path || '#'}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="nav-icon">
                {item.icon || '↗'}
              </span>
              <span>{item.name}</span>
            </a>
          );
        }

        // 内部页面
        return (
          <NavLink
            key={item.id}
            to={item.path || '/'}
            className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`
            }
          >
            <span className="nav-icon">
              {item.icon || '◇'}
            </span>
            <span>{item.name}</span>
          </NavLink>
        );
      });

  return (
    <div
      className={`gateway-shell ${
        collapsed ? 'sidebar-collapsed' : ''
      }`}
    >
      {/* 左侧导航栏 */}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">B</span>
          <span className="brand-name">
            BiSheng <b>Gateway</b>
          </span>
        </div>

        <nav aria-label="主导航">
          <div className="nav-label">
            工作空间
          </div>
          {renderMenus()}
        </nav>

        <div className="sidebar-footer">
          <div className="environment">
            <span className="status-dot online" />
            生产环境
          </div>

          <small>
            v1.0.0 · Gateway API 正常
          </small>
        </div>
      </aside>

      {/* 右侧主工作区 */}
      <section className="app-frame">
        {/* 顶部导航栏 */}
        <header className="topbar">
          <button
            type="button"
            className="icon-button"
            aria-label="折叠导航"
            aria-expanded={!collapsed}
            onClick={() => dispatch(toggleSidebar())}
          >
            ☰
          </button>

          <div className="breadcrumb">
            AI Gateway <span>/</span> {title}
          </div>

          <div className="topbar-actions">
            <button
              type="button"
              className="search-button"
            >
              ⌕ <span>搜索 Agent、报告或会话</span>
              <kbd>⌘ K</kbd>
            </button>

            <button
              type="button"
              className="icon-button"
              aria-label="通知"
            >
              ♧<i className="notification-dot" />
            </button>

            <div className="user-avatar">
              {identity.user.username.slice(0, 1)}
            </div>

            <div className="user-meta">
              <b>{identity.user.username}</b>
              <small>
                {identity.roles
                  .map((role) => role.name)
                  .join('、') || '未分配角色'}
              </small>
            </div>
          </div>
        </header>

        {/* 页面内容由 App.tsx 中的路由组件传入 */}
        <main className="content">
          {children}
        </main>
      </section>
    </div>
  );
}
