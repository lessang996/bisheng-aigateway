from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from app.core.config import get_settings

settings = get_settings()
engine_options = {"pool_pre_ping": True, "echo": False}
if settings.database_url.startswith("sqlite"):
    engine_options["poolclass"] = NullPool
else:
    engine_options.update({
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    })
    engine_options.setdefault("connect_args", {})
    engine_options["connect_args"]["charset"] = "utf8mb4"
engine = create_async_engine(settings.database_url, **engine_options)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app.models import models  # noqa: F401
    if settings.db_auto_create:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)


async def check_database() -> bool:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def close_database() -> None:
    """
    关闭数据库连接池。
    """

    await engine.dispose()
