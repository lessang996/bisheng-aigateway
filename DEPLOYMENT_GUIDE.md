# Bisheng Gateway — 上线部署手册

> 基于仓库后端实现与配置生成。关键参考文件：[Dockerfile](Dockerfile)、[backend/main.py](backend/main.py)、[backend/app/core/config.py](backend/app/core/config.py)、[backend/alembic.ini](backend/alembic.ini)。

## 概要

本文档按生产发布流程组织：镜像准备 → 数据库迁移（Alembic）→ 启动容器 → 验证与监控。

---

## 镜像准备

- 构建镜像（在仓库根目录执行）：

```bash
docker build -t <REGISTRY>/bisheng-gateway:<TAG> .
```

- 推送镜像：

```bash
docker push <REGISTRY>/bisheng-gateway:<TAG>
```

- 说明：镜像基于 `python:3.12-slim`，在容器内创建虚拟环境并运行 `uvicorn main:app`，暴露端口 `8080`（见 [Dockerfile](Dockerfile)）。

---

## 关键环境变量

- `DATABASE_URL`：数据库连接字符串（生产请使用 MySQL/Postgres），示例：

  - MySQL（asyncmy 驱动）: `mysql+asyncmy://user:pass@mysql-host:3306/gateway`

- `REDIS_URL`：例如 `redis://redis:6379/0`
- `JWT_SECRET_KEY`：JWT 对称密钥（若使用 HS256）
- `DB_AUTO_CREATE`：是否允许应用自动创建 DB（生产建议 `false`）
- `DB_REQUIRED`：数据库是否为必需（失败则停止启动）
- `PORT`：应用监听端口（镜像默认 8080）
- `WEB_CONCURRENCY`：uvicorn worker 数量（默认 2）

默认配置在 [backend/app/core/config.py](backend/app/core/config.py) 的 `Settings` 中定义；仓库默认使用 SQLite，仅用于本地开发。

---

## 数据库迁移（Alembic）

> 注意：`backend/alembic.ini` 默认指向 SQLite。部署前请确保 Alembic 使用生产数据库 URL 或在命令中覆盖。

- 在宿主机或 CI 中直接运行迁移：

```bash
DATABASE_URL='mysql+asyncmy://user:pass@host:3306/gateway' \
  alembic -c backend/alembic.ini upgrade head
```

- 使用镜像运行迁移（推荐在 CI/CD 发布步骤以镜像为基础执行）：

```bash
docker run --rm \
  -e DATABASE_URL='mysql+asyncmy://user:pass@host:3306/gateway' \
  --workdir /app/backend \
  <REGISTRY>/bisheng-gateway:<TAG> \
  /app/backend/.venv/bin/alembic -c alembic.ini upgrade head
```

- 在运行容器内执行（不推荐用于自动化）：

```bash
docker exec -it <container_name> \
  /app/backend/.venv/bin/alembic -c /app/backend/alembic.ini upgrade head
```

- 运营建议：生产环境应在部署前由运维或 CI 完成数据库创建与迁移，设置 `DB_AUTO_CREATE=false`，并保留迁移回滚/备份策略。

---

## 启动容器示例（单机）

- 最小运行：

```bash
docker run -d --name bisheng-gateway \
  -p 8080:8080 \
  -e DATABASE_URL='mysql+asyncmy://user:pass@mysql:3306/gateway' \
  -e REDIS_URL='redis://redis:6379/0' \
  -e JWT_SECRET_KEY='replace-with-secret' \
  -e DB_AUTO_CREATE=false \
  -e PORT=8080 \
  --restart unless-stopped \
  <REGISTRY>/bisheng-gateway:<TAG>
```

- 推荐的网络与日志卷配置：

```bash
docker network create gateway-net

docker run -d --name bisheng-gateway \
  --network gateway-net \
  -p 8080:8080 \
  -v /var/log/bisheng:/app/backend/logs \
  -e DATABASE_URL='mysql+asyncmy://user:pass@mysql:3306/gateway' \
  -e REDIS_URL='redis://redis:6379/0' \
  -e JWT_SECRET_KEY='...' \
  -e DB_AUTO_CREATE=false \
  --restart unless-stopped \
  <REGISTRY>/bisheng-gateway:<TAG>
```

说明：镜像内以非 root 用户（UID 10001）运行，挂载外部卷时注意权限问题以便容器写日志。

---

## Docker Compose 示例

将下列示例作为参考并按安全规范调整密码与持久化策略：

```yaml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: example
      MYSQL_DATABASE: gateway
      MYSQL_USER: gateway
      MYSQL_PASSWORD: gatewaypass
    volumes:
      - db-data:/var/lib/mysql
    networks:
      - gateway-net

  redis:
    image: redis:7
    networks:
      - gateway-net

  gateway:
    image: <REGISTRY>/bisheng-gateway:<TAG>
    depends_on:
      - mysql
      - redis
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: "mysql+asyncmy://gateway:gatewaypass@mysql:3306/gateway"
      REDIS_URL: "redis://redis:6379/0"
      JWT_SECRET_KEY: "replace-with-secret"
      DB_AUTO_CREATE: "false"
    networks:
      - gateway-net
    restart: unless-stopped

volumes:
  db-data:

networks:
  gateway-net:
```

在 Compose 中执行迁移：

```bash
docker-compose run --rm gateway \
  /app/backend/.venv/bin/alembic -c /app/backend/alembic.ini upgrade head
```

---

## 健康检查与日志

- 健康端点：
  - 存活：`/health/live`
  - 就绪：`/health/ready`

  示例验证：

```bash
curl -f http://localhost:8080/health/ready
```

- 查看容器日志：

```bash
docker logs -f bisheng-gateway
```

- 镜像内日志默认路径：`/app/backend/logs/gateway.log`（可挂载到宿主以便持久化与采集）。

---

## 安全与运维建议

- 请勿在仓库中提交真实密钥；通过 CI/CD 或容器编排层注入 `DATABASE_URL`、`JWT_SECRET_KEY`、`REDIS_URL` 等敏感信息。
- 在执行迁移前务必做数据库备份；在更改 schema 前确认向后兼容性或准备回滚计划。
- 将 `DB_REQUIRED` 设置为 `true` 可避免在数据库不可用时错误启动；根据业务策略选择容错或严格失败模式。

---

## 快速检查清单（发布前）

- 镜像构建并推送：`docker push <REGISTRY>/bisheng-gateway:<TAG>`
- 数据库已创建并备份
- 执行 Alembic 迁移：`alembic upgrade head` 或等效命令
- 启动容器并验证 `/health/ready`
- 日志与监控已配置

---

## 下一步（可选）

- 我可以：
  1. 基于上面内容生成 `deploy/run-migrations.sh` 与 `deploy/compose-prod.yml` 并提交到仓库；
  2. 或仅将本文件提交为 PR。请告诉我你的偏好。
