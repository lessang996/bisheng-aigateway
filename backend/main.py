import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.apis.router import api_router
from app.core.config import get_settings
from app.core.logger import setup_logging
from app.core.redis import get_report_cache
from app.db.session import check_database, close_database, engine, init_db
from app.exceptions.errors import GatewayError
from app.exceptions.handlers import gateway_exception_handler
from app.middleware import (
    BodySizeLimitMiddleware,
    JWTMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SensitiveFilterMiddleware,
)
from app.utils.http_client import create_http_client

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


# ============================================================
# Application Lifespan
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None,None]:
    """
    FastAPI 应用生命周期管理。

    startup: 初始化数据库、Redis 及其他连接池
    shutdown: 释放 HTTP client、Redis、DB 等资源
    """
    logger.info("starting gateway service: %s", settings.app_name)

    # --- Startup ---
    try:
        await init_db()
        await check_database()
        logger.info("database initialized successfully")
    except Exception:
        logger.exception("database initialization failed")
        db_required = getattr(settings, "db_required", False)
        if db_required:
            logger.critical("database is required, abort startup")
            raise
        logger.warning(
            "database unavailable, continuing startup because db_required=false"
        )

    try:
        redis_cache = get_report_cache()
        await redis_cache.client.ping()
        app.state.redis = redis_cache
        logger.info("redis connection initialized")
    except Exception:
        app.state.redis = None
        logger.warning(
            "redis initialization failed; continuing without cache", exc_info=True
        )

    # TODO: 初始化其他全局资源 (HTTP Client, Model Client 等)
    app.state.http_client = create_http_client()
    logger.info("http client initialized")
    logger.info("gateway startup completed")

    try:
        yield
    finally:
        # --- Shutdown ---
        logger.info("gateway shutdown started")
        http_client = getattr(app.state, "http_client", None)
        if http_client:
            try:
                await http_client.close()
            except Exception:
                logger.warning(
                    "http client shutdown failed",
                    exc_info=True,
                )
                

        if app.state.redis is not None:
            try:
                await app.state.redis.close()
            except Exception:
                logger.warning("redis shutdown failed", exc_info=True)
     
        try:
            await close_database()
        except Exception:
            logger.warning(
                "database engine shutdown failed",
                exc_info=True,
            )

        logger.info("gateway shutdown completed")


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path_in_servers=False,
)

# ============================================================
# CORS Configuration
# ============================================================

cors_origins = settings.cors_origin_list or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Middleware Stack
# ============================================================
# 注意: Starlette/FastAPI 中间件执行顺序为「后添加先执行」(LIFO)
#
# 实际请求处理链路:
#   RequestContext → RateLimit → JWT → SensitiveFilter → BodySizeLimit → Router
#

# app.add_middleware(BodySizeLimitMiddleware)
# app.add_middleware(SensitiveFilterMiddleware)
app.add_middleware(JWTMiddleware)

# Rate Limit 配置解析
# try:
#     rate_limit = int(str(settings.rate_limit).split("/", 1)[0])
# except (ValueError, AttributeError):
#     logger.warning("invalid rate_limit=%r, fallback to 100", settings.rate_limit)
#     rate_limit = 100

# app.add_middleware(RateLimitMiddleware, limit=rate_limit)
# app.add_middleware(RequestContextMiddleware)

# ============================================================
# Exception Handlers
# ============================================================

app.add_exception_handler(GatewayError, gateway_exception_handler)


# ============================================================
# Routers
# ============================================================

app.include_router(api_router)
