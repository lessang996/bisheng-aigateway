"""Run after migrations: python -m app.init.rbac --admin cqbank."""
import argparse
import asyncio
from app.db.session import SessionLocal
from app.services.rbac import seed_rbac


async def initialize(administrator):
    async with SessionLocal() as db:
        await seed_rbac(db, administrator=administrator)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='初始化角色、权限、菜单并授权已有管理员账号')
    parser.add_argument('--admin', default='cqbank')
    args = parser.parse_args()
    asyncio.run(initialize(args.admin))
