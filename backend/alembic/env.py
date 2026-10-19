"""Alembic runner supports existing async MySQL/SQLite configuration."""
import asyncio
import sys
from pathlib import Path
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.models import models  # noqa: F401

target_metadata = SQLModel.metadata
config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=connection.dialect.name == 'sqlite')
    with context.begin_transaction():
        context.run_migrations()


async def online():
    url = config.attributes.get('database_url') or get_settings().database_url
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError('此兼容迁移需要读取现有表结构，请使用在线迁移模式')
elif config.attributes.get('connection') is not None:
    run(config.attributes['connection'])
else:
    asyncio.run(online())
