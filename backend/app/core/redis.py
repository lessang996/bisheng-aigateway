"""Redis-backed cache for completed industry-report SSE streams."""

import json
import logging
from typing import Any, Optional

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore[assignment,misc]

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(
        self,
        redis_url: str,
        ttl: int,
        key_prefix: str = "",
        **kwargs: Any,
    ) -> None:
        if Redis is None:
            raise RuntimeError("redis package is not installed")

        self._ttl = ttl
        self._prefix = key_prefix

        self.client = Redis.from_url(
            redis_url,
            decode_responses=True,
            **kwargs,
        )

    def _make_key(self, key: str) -> str:
        if self._prefix:
            return f"{self._prefix}{key}"
        return key

    async def get_json(self, key: str) -> Optional[Any]:
        try:
            value = await self.client.get(self._make_key(key))

            if value is None:
                return None

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Invalid JSON in Redis cache: key=%s",
                    self._make_key(key),
                )
                return None

        except Exception:
            logger.exception(
                "Redis cache get failed: key=%s",
                self._make_key(key),
            )
            return None

    async def set_json(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        expire = self._ttl if ttl is None else ttl

        try:
            await self.client.set(
                self._make_key(key),
                serialized,
                ex=expire,
            )
        except Exception:
            logger.exception(
                "Redis cache set failed: key=%s",
                self._make_key(key),
            )

    async def close(self) -> None:
        await self.client.aclose()


# 显式单例
_cache_instance: Optional[RedisCache] = None


def get_report_cache() -> RedisCache:
    global _cache_instance

    if _cache_instance is None:
        settings = get_settings()

        _cache_instance = RedisCache(
            redis_url=settings.redis_url,
            ttl=settings.redis_cache_ttl,
            key_prefix=getattr(
                settings,
                "redis_cache_key_prefix",
                "report:",
            ),
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )

    return _cache_instance


async def reset_report_cache() -> None:
    """
    用于测试、应用关闭或重新初始化时释放 Redis 连接。
    """
    global _cache_instance

    if _cache_instance is not None:
        await _cache_instance.close()
        _cache_instance = None
