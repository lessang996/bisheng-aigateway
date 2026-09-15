import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request):
    checks = {"database": False, "redis": False}
    try:
        await check_database()
        checks["database"] = True
    except Exception:
        logger.warning("database readiness check failed", exc_info=True)
    redis_cache = getattr(request.app.state, "redis", None)
    if redis_cache is not None:
        try:
            checks["redis"] = bool(await redis_cache.client.ping())
        except Exception:
            logger.warning("redis readiness check failed", exc_info=True)
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
