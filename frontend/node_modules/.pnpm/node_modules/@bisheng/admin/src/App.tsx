import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Authorized } from './access';
import ManagementPage from './pages/ManagementPage';
import StatisticsPage from './pages/StatisticsPage';
import BasicLayout from './layouts/BasicLayout';
import LoginPage from './pages/LoginPage';
import StatePage from './pages/StatePage';
import ConversationPage from './pages/ConversationPage';

const GatewayPage = lazy(() => import('../../../src/pages/industry-report'));

function Protected({ children }: { children: React.ReactNode }) {
  return <Authorized><BasicLayout>{children}</BasicLayout></Authorized>;
}

export default function App() {
  return (
    <Suspense
      fallback={
        <div className="content">
          <div className="panel">正在加载工作台…</div>
        </div>
      }
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Protected><GatewayPage /></Protected>} />
        <Route path="/reports" element={<Protected><GatewayPage /></Protected>} />
        <Route path="/agents" element={<Protected><StatePage title="Agent 管理" description="Agent 编排、模型配置与运行状态将在此统一管理。" /></Protected>} />
        <Route path="/agents/:id" element={<Protected><StatePage title="Agent 详情" description="查看模型配置、Prompt、Capabilities、知识库与调用统计。" /></Protected>} />
        <Route path="/conversations" element={<Protected><ConversationPage /></Protected>} />
        <Route path="/conversations/:id" element={<Protected><ConversationPage /></Protected>} />
        <Route path="/knowledge" element={<Protected><StatePage title="知识库" description="管理企业知识源、索引和检索配置。" /></Protected>} />
        <Route path="/users" element={<Protected><ManagementPage key="users" resource="users" /></Protected>} />
        <Route path="/roles" element={<Protected><ManagementPage key="roles" resource="roles" /></Protected>} />
        <Route path="/permissions" element={<Protected><ManagementPage key="permissions" resource="permissions" /></Protected>} />
        <Route path="/system/health" element={<Protected><StatePage title="系统健康" description="查看 Gateway、Redis、Database、BiSheng、LLM 和 SSE 状态。" /></Protected>} />
        <Route path="/system/logs" element={<Protected><StatePage title="系统日志" description="查看请求、错误与审计日志。" /></Protected>} />
        <Route path="/system/settings" element={<Protected><StatePage title="系统设置" description="管理网关运行参数和环境配置。" /></Protected>} />
        <Route path="/menus" element={<Protected><ManagementPage key="menus" resource="menus" /></Protected>} />
        <Route path="/stats" element={<Protected><StatisticsPage /></Protected>} />
        <Route path="/403" element={<StatePage title="无权访问" description="当前账号没有访问该页面的权限。" />} />
        <Route path="*" element={<StatePage title="页面不存在" description="请检查访问地址或返回工作台。" />} />
      </Routes>
    </Suspense>
  );
}