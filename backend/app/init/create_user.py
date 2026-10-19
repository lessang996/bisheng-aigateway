"""Explicit operator account creation before RBAC initialization; grants no roles."""
import argparse
import asyncio
import os

from sqlmodel import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.models import User


async def create_user(username: str):
    password = os.environ.get('BOOTSTRAP_USER_PASSWORD', '')
    if not username.strip() or not 8 <= len(password.encode('utf-8')) <= 72:
        raise ValueError('请指定用户名，并通过 BOOTSTRAP_USER_PASSWORD 提供 8 至 72 字节的密码')
    async with SessionLocal() as db:
        if (await db.execute(select(User.id).where(User.username == username))).first():
            raise ValueError('账号已存在；此命令不会覆盖密码或权限')
        db.add(User(username=username, email=f'{username}@local', password_hash=hash_password(password)))
        await db.commit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='由部署人员显式创建账号，不授予角色')
    parser.add_argument('--username', required=True)
    asyncio.run(create_user(parser.parse_args().username))
