# Bisheng Gateway

基于 FastAPI、SQLModel、异步 SQLAlchemy、Redis、React 和 Vite 的模型 API 网关，提供 JWT、SSE 转发、调用统计和敏感信息过滤。

## 目录

- `backend/`：后端应用、Alembic、测试及 Python 依赖
- `frontend/`：行业分析报告 React 页面
- `k8s/`：Kubernetes 部署清单

## 后端

```powershell
cd backend
uv sync --group dev
Copy-Item .env.example .env
uv run uvicorn main:app --reload
```

Swagger：`http://localhost:8000/docs`；健康检查：`/health`。

数据库迁移和测试均从 `backend/` 执行：

```powershell
uv run alembic upgrade head
uv run pytest
```

## 前端

```powershell
cd frontend
npm install
npm run dev
```

开发服务器将 `/api` 代理到 `VITE_API_BASE_URL`，默认地址为 `http://localhost:8000`。

## Docker

先将 `backend/.env.example` 复制为 `backend/.env` 并填写运行环境配置，然后执行：

```powershell
docker compose up --build
```
