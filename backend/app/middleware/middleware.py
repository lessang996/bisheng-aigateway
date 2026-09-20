import re
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import decode_token
from app.exceptions.errors import AuthenticationError


class JWTMiddleware(BaseHTTPMiddleware):
    """Optionally decodes a bearer access token and exposes its claims."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        auth_header = request.headers.get("Authorization", "")
        scheme, _, credentials = auth_header.partition(" ")
        token = credentials.strip() if scheme.lower() == "bearer" else ""

        request.state.user = None
        if token:
            try:
                request.state.user = decode_token(token, expected_type="access")
            except AuthenticationError:
                pass

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, limit: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.hits: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        now = time.time()
        key = request.client.host if request.client else "unknown"

        # Filter out expired hits within the 60s window
        values = [x for x in self.hits.get(key, []) if now - x < 60]

        if len(values) >= self.limit:
            from app.exceptions.errors import RateLimitError

            raise RateLimitError("Rate limit exceeded")

        values.append(now)
        self.hits[key] = values
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.6f}"
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        length = request.headers.get("content-length")
        max_size = get_settings().max_body_size

        if length and int(length) > max_size:
            from fastapi import HTTPException

            raise HTTPException(status_code=413, detail="Request body too large")

        return await call_next(request)


class SensitiveFilterMiddleware(BaseHTTPMiddleware):
    PATTERNS = [
        re.compile(r'(?i)(password|api[_-]?key|access[_-]?token|secret)["\']?\s*[:=]\s*["\']?[^,\s"\'}]+'),
        re.compile(r"\b\d{11}\b"),
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    ]

    SKIP_PATHS = frozenset(["/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"])

    @classmethod
    def scrub(cls, text: str) -> str:
        for pattern in cls.PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        settings = get_settings()

        should_skip = (
            request.url.path in self.SKIP_PATHS
            or not settings.sensitive_filter_enabled
            or "text/event-stream" in content_type
        )
        if should_skip:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        scrubbed_content = self.scrub(body.decode("utf-8", errors="ignore")).encode()

        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)
        headers.pop("etag", None)

        return Response(
            content=scrubbed_content,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
            background=response.background,
        )
