# 行业报告统计与权限部署

保留现有 SSE、非流式 JSON 和 Redis 缓存键及共享范围。每条问题消息代表一次调用；回答通过 `parent_id` 关联。缓存命中率仅以命中和未命中为分母，读取失败不计入；历史不确定记录保持未知，不估算耗时。日期筛选和日/月分组使用北京时间，数据库时间使用 UTC。

## 部署顺序

### 一步初始化管理员

在 `backend` 目录执行迁移后，可以使用新脚本一次完成账号创建和管理员授权：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
# 新账号需要预先通过安全环境变量注入 BOOTSTRAP_USER_PASSWORD（8 至 72 字节）。
.venv\Scripts\python.exe -m app.init.admin --username cqbank
Remove-Item Env:BOOTSTRAP_USER_PASSWORD -ErrorAction SilentlyContinue
```

省略 `--username` 时默认使用 `cqbank`。账号不存在则创建；账号存在则仅授权，保留原密码、部门和登录方式。重复执行不重复授权或审计；停用账号或停用管理员角色会报错，不自动启用。脚本使用项目配置的 `DATABASE_URL`，不自动建表、不输出密码；以下分步命令也仍可使用。

先备份数据库，在数据副本上验证迁移，再发布应用。生产配置 `DB_AUTO_CREATE=false`，通过环境变量提供数据库、Redis 和认证配置。以下命令在 `backend` 目录执行：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app.init.rbac --admin cqbank
```

初始化要求 `cqbank` 已存在且启用，不存在会明确报错。空库由部署人员先通过安全环境变量注入 `BOOTSTRAP_USER_PASSWORD`，再执行：

```powershell
.venv\Scripts\python.exe -m app.init.create_user --username cqbank
.venv\Scripts\python.exe -m app.init.rbac --admin cqbank
Remove-Item Env:BOOTSTRAP_USER_PASSWORD
```

创建命令不覆盖已有账号、不授予角色、不使用默认密码。普通登录不会按用户名提权。首次初始化给已有账号分配普通角色，并给指定账号追加管理员；再次运行不覆盖人工角色配置或恢复已移除的普通角色。显式 `--admin` 授权仍会追加管理员角色。所有管理员权限均由有效管理员角色决定。

## 管理入口

- `/stats`：概览、按用户/部门/日/月/缓存统计、分页明细和问题回答详情。
- `/users`、`/roles`、`/permissions`、`/menus`：账号、角色授权、权限编码及导航管理。
- 用户可拥有多个角色，数据范围取并集；无部门账号的部门范围不会匹配其他空部门账号。
- 菜单只支持已注册页面和 HTTP/HTTPS 外链；新增权限编码需接入实际业务检查点才生效。
- 权限在后端每次请求从数据库读取，前端导航重新加载身份；停用用户和吊销 Token 会被拒绝。
- 进程异常退出留下的处理中记录不会自动判成功。迁移兼容旧 `redis_cache` 回答；无法确认的历史信息保留未知。

迁移会保留旧表及记录，并补齐字段、索引、RBAC 表。旧 metadata 非法 JSON 在 MySQL 转换时保存到 `legacy_raw`，不丢弃原文。迁移不支持自动降级删除授权数据；回退请恢复迁移前备份。SQLite 的空库和旧表测试不能替代目标 MySQL 版本及生产数据副本验证。

## 检查

```powershell
# backend：建议使用隔离测试数据库
.venv\Scripts\python.exe -m pytest tests
# frontend
pnpm --filter @bisheng/admin typecheck
pnpm --filter @bisheng/admin build
```

自动化测试使用模拟上游及临时 SQLite，覆盖缓存、流式终态、权限范围、管理保护和迁移。上线前另行完成真实上游/Redis/MySQL 联调及浏览器验收：普通账号菜单和直接访问 403、统计筛选详情、账号角色菜单编辑及授权后下一请求生效。
