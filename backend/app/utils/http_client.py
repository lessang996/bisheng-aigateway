import asyncio
import contextlib
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Request

from app.core.config import get_settings
from app.exceptions.errors import ExternalServiceError

logger = logging.getLogger(__name__)


def _safe_url(url: str) -> str:
    """Return a URL suitable for logs without query parameters or fragments."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class CircuitBreaker:
    """
    简单的熔断器

    规则：
    - 连续失败达到 threshold 后打开熔断
    - recovery 秒后允许再次尝试
    - 成功后清零失败次数
    """

    def __init__(self, threshold: int = 5, recovery: int = 30):
        self.threshold = threshold
        self.recovery = recovery
        self.failures = 0
        self.opened_at: float | None = None

    def allow(self) -> bool:
        now = asyncio.get_running_loop().time()

        # 熔断已经打开
        if self.opened_at is not None:
            elapsed = now - self.opened_at

            # 还在恢复时间内
            if elapsed < self.recovery:
                return False

            # 恢复时间到了，允许尝试一次
            self.opened_at = None
            self.failures = 0

        return True

    def success(self):
        self.failures = 0
        self.opened_at = None

    def failure(self):
        self.failures += 1

        if self.failures >= self.threshold:
            self.opened_at = asyncio.get_running_loop().time()


class HTTPClient:
    """
    统一 HTTP Client

    功能：
    - Bearer Token
    - 公共 Header
    - Timeout
    - Retry
    - Circuit Breaker
    - Connection Pool
    """

    def __init__(self):
        self.settings = get_settings()

        self.breaker = CircuitBreaker(
            threshold=self.settings.circuit_breaker_failure_threshold,
            recovery=self.settings.circuit_breaker_recovery_seconds,
        )

        # HTTPX Timeout
        self.timeout = httpx.Timeout(
            connect=self.settings.external_timeout_connect,
            read=self.settings.external_timeout_read,
            write=getattr(
                self.settings,
                "external_timeout_write",
                self.settings.external_timeout_read,
            ),
            pool=getattr(
                self.settings,
                "external_timeout_pool",
                10.0,
            ),
        )

        # 连接池
        self.limits = httpx.Limits(
            max_connections=getattr(
                self.settings,
                "external_max_connections",
                100,
            ),
            max_keepalive_connections=getattr(
                self.settings,
                "external_max_keepalive_connections",
                20,
            ),
        )

        self.client = httpx.AsyncClient(
            proxy=None,
            timeout=self.timeout,
            limits=self.limits,
        )

    def _build_headers(
        self,
        headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        构造请求 Header

        优先级：
        业务传入 Header
        >
        默认 Bearer Token
        """

        result = {}

        # 默认 Bearer Token
        upstream_token = getattr(
            self.settings,
            "upstream_bearer_token",
            None,
        )

        if upstream_token:
            result["Authorization"] = f"Bearer {upstream_token}"

        # 业务 Header 覆盖默认 Header
        if headers:
            result.update(headers)

        return result

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:

        if not self.breaker.allow():
            raise ExternalServiceError(
                "External service circuit is open"
            )

        request_headers = self._build_headers(headers)
        logger.info('HTTPClient request method=%s url=%s', method, _safe_url(url))
        last_exception = None

        retry_count = self.settings.external_retries

        for attempt in range(retry_count + 1):
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=request_headers,
                    **kwargs,
                )

                response.raise_for_status()

                # 整个业务请求成功
                self.breaker.success()

                return response

            except httpx.HTTPStatusError as exc:
                last_exception = exc

                # HTTP 4xx 一般不应该重试
                if exc.response.status_code < 500:
                    raise ExternalServiceError(
                        f"External service returned "
                        f"{exc.response.status_code}",
                    ) from exc

            except httpx.TimeoutException as exc:
                last_exception = exc

            except httpx.RequestError as exc:
                last_exception = exc

            # Retry
            if attempt < retry_count:
                backoff = (
                    self.settings.external_retry_backoff
                    * (2 ** attempt)
                )

                await asyncio.sleep(backoff)

        # 所有 retry 都失败
        self.breaker.failure()

        raise ExternalServiceError(
            "External service request failed",
        ) from last_exception

    async def get(self, url: str, **kwargs):
        return await self.request(
            "GET",
            url,
            **kwargs,
        )

    async def post(self, url: str, **kwargs):
        return await self.request(
            "POST",
            url,
            **kwargs,
        )

    async def put(self, url: str, **kwargs):
        return await self.request(
            "PUT",
            url,
            **kwargs,
        )

    async def delete(self, url: str, **kwargs):
        return await self.request(
            "DELETE",
            url,
            **kwargs,
        )

    @contextlib.asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """
        SSE / HTTP 流式请求

        与普通 request() 分开：
        - 普通 HTTP 请求继续使用原来的 timeout
        - SSE 使用独立的 stream timeout
        - read=None，避免长时间无数据导致 ReadTimeout
        """

        if not self.breaker.allow():
            raise ExternalServiceError(
                "External service circuit is open"
            )

        request_headers = self._build_headers(headers)

        logger.info(
            "HTTPClient stream request "
            "method=%s url=%s",
            method,
            _safe_url(url),
        )

        # SSE 长连接不设置 read timeout
        stream_timeout = httpx.Timeout(
            connect=self.timeout.connect,
            read=None,
            write=self.timeout.write,
            pool=self.timeout.pool,
        )

        try:

            async with self.client.stream(
                method,
                url,
                headers=request_headers,
                timeout=stream_timeout,
                **kwargs,
            ) as response:

                # HTTP 状态码检查
                if response.status_code >= 400:

                    await response.aread()
                    raise ExternalServiceError(
                        f"External service returned "
                        f"{response.status_code}",
                    )

                # SSE HTTP 连接建立成功
                self.breaker.success()

                yield response

        except asyncio.CancelledError:
            logger.info(
                "HTTPClient stream cancelled "
                "method=%s url=%s",
                method,
                _safe_url(url),
            )
            raise

        except ExternalServiceError:
            raise

        except httpx.TimeoutException as exc:

            self.breaker.failure()

            logger.warning(
                "HTTPClient stream timeout method=%s url=%s error=%s",
                method,
                _safe_url(url),
                type(exc).__name__,
            )

            raise ExternalServiceError("External service stream timeout") from exc

        except httpx.RequestError as exc:

            self.breaker.failure()

            logger.warning(
                "HTTPClient stream request failed method=%s url=%s error=%s",
                method,
                _safe_url(url),
                type(exc).__name__,
            )

            raise ExternalServiceError("External service stream request failed") from exc

    async def close(self):
        await self.client.aclose()



def create_http_client() -> HTTPClient:
    return HTTPClient()


async def get_http_client(request: Request) -> HTTPClient:
    client = getattr(request.app.state, "http_client", None)

    if client is None:
        raise RuntimeError("HTTP client is not initialized")

    return client
