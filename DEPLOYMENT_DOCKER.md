# Docker 生产部署

## 构建

```bash
docker build --pull -t bisheng-gateway:<version> .
```

镜像采用多阶段构建，仅包含 Python 运行时、锁定的生产依赖和 `backend/` 代码，以 UID 10001 非 root 用户运行。

## 启动

生产环境必须通过环境变量注入配置（不要把真实值写入镜像或仓库）：

```bash
docker run -d --name bisheng-gateway --restart=unless-stopped \
  -p 8000:8000 -e ENVIRONMENT=production -e DB_AUTO_CREATE=false \
  -e DATABASE_URL='mysql+aiomysql://USER:PASSWORD@mysql:3306/gateway?charset=utf8mb4' \
  -e REDIS_URL='redis://:PASSWORD@redis:6379/0' \
  -e JWT_SECRET_KEY='use-a-long-random-secret' \
  -e EXTERNAL_API_URL='https://router.fis.aliyuncs.com/finx/api' \
  -e EXTERNAL_API_KEY='...' -e UPSTREAM_BEARER_TOKEN='...' \
  bisheng-gateway:<version>
```

在发布流水线中先执行 `docker run --rm --entrypoint alembic bisheng-gateway:<version> -c /app/backend/alembic.ini upgrade head`，再启动应用。MySQL 和 Redis 应使用独立的持久化生产服务。健康检查使用 `/health/live`，流量接入应等待 `/health/ready` 返回 200；通过 `WEB_CONCURRENCY` 调整 worker 数量。
