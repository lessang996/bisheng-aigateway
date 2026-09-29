# BiSheng Gateway Admin

企业 AI Gateway 管理平台前端，采用 pnpm workspace、React、TypeScript、Vite、React Router、Ant Design、Redux Toolkit、TanStack Query 与 UnoCSS。

## Workspace

- `apps/admin`: 管理端应用、路由、布局和页面组合
- `packages/api`: 统一 JSON/SSE API Client 与业务 API 模块
- `packages/auth`: Token 存储和 Authorization 注入
- `packages/config`: 环境变量入口
- `packages/sse`: SSE 解析与流式协议边界
- `packages/types`: 跨包类型
- `packages/ui`: 可复用基础组件
- `packages/mock`: Demo 数据适配层

## Commands

```bash
pnpm install
pnpm dev
pnpm typecheck
pnpm build
```

复制 `.env.example` 为 `.env.development`，默认 API 代理指向 `/api`。报告中心保留 FastAPI `POST /api/chat/report` SSE 合同，登录使用 `POST /api/auth/login`。
