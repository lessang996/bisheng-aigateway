import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import { Provider } from 'react-redux';
import { BrowserRouter } from 'react-router-dom';
import { store } from './store';
import App from './App';
import '../../../src/assets/styles/global.css';
import 'uno.css';

// 创建 React Query 客户端实例
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 数据缓存 30 秒后视为过期
      retry: 1,         // 请求失败后重试 1 次
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider
          theme={{
            token: {
              colorPrimary: '#1677ff',
              borderRadius: 6,
              colorBgLayout: '#f5f7fa',
            },
          }}
        >
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ConfigProvider>
      </QueryClientProvider>
    </Provider>
  </StrictMode>
);