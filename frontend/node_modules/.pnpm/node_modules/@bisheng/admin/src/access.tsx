import {
  createContext,
  useContext,
  type ReactNode,
} from 'react';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@bisheng/api';
import { tokenStore } from '@bisheng/auth';

import { Alert, Button, Spin } from 'antd';
import { Navigate, useLocation } from 'react-router-dom';

/**
 * 菜单项类型
 */
export type MenuItem = {
  id: number;
  name: string;
  path: string | null;
  parent_id: number | null;
  kind: 'directory' | 'page' | 'external';
  icon: string;
  permission_code: string | null;
  sort_order: number;
};

/**
 * 当前登录用户的身份和权限信息
 */
export type Identity = {
  user: {
    id: number;
    username: string;
    department: string | null;
  };
  roles: {
    id: number;
    name: string;
  }[];
  permissions: string[];
  menus: MenuItem[];
  is_admin: boolean;
};

/**
 * 权限上下文
 *
 * 用于在组件树中共享当前用户的身份、角色、
 * 权限和菜单信息。
 */
const AccessContext = createContext<Identity | null>(null);

/**
 * 获取当前用户的权限上下文
 */
export const useAccess = () => useContext(AccessContext)!;

/**
 * 路由与权限编码的映射关系
 */
export const routePermission: Record<string, string> = {
  '/dashboard': 'dashboard:view',
  '/reports': 'report:use',
  '/conversations': 'conversation:view',
  '/stats': 'stats:view',
  '/agents': 'agent:view',
  '/knowledge': 'knowledge:view',

  '/users': 'users:manage',
  '/roles': 'roles:manage',
  '/permissions': 'permissions:manage',
  '/menus': 'menus:manage',

  '/system/health': 'system:view',
  '/system/logs': 'logs:view',
  '/system/settings': 'system:manage',
};

/**
 * 路由访问权限控制组件
 */
export function Authorized({children,}: {
  children: ReactNode;
}) {
  // 当前路由信息
  const location = useLocation();

  // 获取本地登录令牌
  const token = tokenStore.get();

  // 查询当前用户的身份和权限
  const query = useQuery({
    queryKey: ['identity', token, location.pathname],

    queryFn: () => apiClient.json<Identity>('/auth/me'),
    // 仅在存在令牌时请求接口
    enabled: !!token,
    // 数据立即视为过期
    staleTime: 0,
    // 关闭 React Query 自动重试
    retry: false,
  });

  // 未登录：跳转登录页面
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // 正在加载用户权限
  if (query.isPending) {
    return <Spin fullscreen />;
  }

  // 获取用户权限失败
  if (query.isError) {
    return (
      <Alert
        type="error"
        message="无法加载账号权限"
        description={query.error.message}
        action={
          <Button onClick={() => void query.refetch()}>
            重试
          </Button>
        }
      />
    );
  }

  // 当前用户的身份信息
  const identity = query.data;

  // 查找匹配当前路径的权限规则
  // 优先匹配路径更长、更具体的规则
  const path = Object.keys(routePermission)
    .sort((a, b) => b.length - a.length)
    .find(
      (p) =>
        location.pathname === p ||
        location.pathname.startsWith(p + '/'),
    );

  // 没有匹配的规则，或者没有相应权限
  if (
    !path ||
    (
      !identity.is_admin &&
      !identity.permissions.includes(routePermission[path])
    )
  ) {
    return <Navigate to="/403" replace />;
  }

  // 授权通过：向子组件提供身份和权限信息
  return (
    <AccessContext.Provider value={identity}>
      {children}
    </AccessContext.Provider>
  );
}