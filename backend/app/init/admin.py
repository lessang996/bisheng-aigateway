"""Create an account if needed and explicitly grant administrator access."""
import argparse
import asyncio
import os

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.models import AuditLog, Role, User, UserRole
from app.services.rbac import seed_rbac


async def initialize_admin(username: str = 'cqbank') -> bool:
    """Return whether the account was created; preserve existing credentials."""
    if not username or username != username.strip() or len(username) > 100:
        raise ValueError('用户名须为 1 至 100 个字符，且首尾不能含空格')
    async with SessionLocal() as db:
        admin_role = (await db.execute(select(Role).where(Role.code == 'admin'))).scalar_one_or_none()
        if admin_role is not None and not admin_role.is_active:
            raise ValueError('管理员角色已停用，请先通过角色管理启用')
        account = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        created = account is None
        if account is not None:
            if account.username != username:
                raise ValueError('用户名大小写与已有账号不一致')
            if not account.is_active:
                raise ValueError('账号已停用，请先通过用户管理启用')
        else:
            password = os.environ.get('BOOTSTRAP_USER_PASSWORD', '')
            if not password.strip() or not 8 <= len(password.encode('utf-8')) <= 72:
                raise ValueError('新账号需要通过 BOOTSTRAP_USER_PASSWORD 提供 8 至 72 字节的非空白密码')
            account = User(username=username, email=f'{username}@local',
                           password_hash=hash_password(password), is_active=True, local_login_enabled=True)
            db.add(account)
            await db.flush()
        granted = admin_role is not None and await db.get(UserRole, (account.id, admin_role.id)) is not None
        if not granted:
            db.add(AuditLog(user_id=account.id, action='initialize_admin',
                            resource=f'users/{account.id}', details='{"source":"operator_cli"}'))
        # seed_rbac commits the account, grants and audit in the same transaction.
        await seed_rbac(db, administrator=username)
        return created


def main():
    parser = argparse.ArgumentParser(description='创建并初始化管理员（默认 cqbank）；须先执行 Alembic 迁移')
    parser.add_argument('--username', default='cqbank', help='管理员用户名，默认 cqbank')
    args = parser.parse_args()
    try:
        created = asyncio.run(initialize_admin(args.username))
    except ValueError as exc:
        parser.exit(1, f'初始化失败：{exc}\n')
    except SQLAlchemyError:
        # Database exceptions may contain credentials or bound password hashes.
        parser.exit(1, '初始化失败：请检查数据库连接、表结构迁移及账号唯一性约束。\n')
    print('管理员初始化成功：' + ('已创建账号并授权。' if created else '已授权，原密码及登录方式保持不变。'))


if __name__ == '__main__':
    main()
