import logging

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError

logger = logging.getLogger(__name__)


def extract_token(request: Request) -> str | None:
    """
    提取 JWT Token。

    仅支持标准 Authorization: Bearer <token>，避免 Token 出现在 URL、
    浏览器历史、代理日志和访问日志中。
    """

    auth_header = request.headers.get("Authorization", "").strip()

    if auth_header:
        scheme, _, credentials = auth_header.partition(" ")

        if scheme.lower() == "bearer":
            token = credentials.strip()

            if token:
                return token

    return None

async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    验证当前请求的 Access Token，并返回 JWT Claims。
    """

    token = extract_token(request)

    if not token:
        raise AuthenticationError(
            "Authentication required"
        )

    # 先验证 JWT 签名、过期时间和 token type
    try:
        payload = decode_token(
            token,
            expected_type="access",
        )
    except AuthenticationError as exc:
        logger.warning(
            "JWT authentication failed path=%s error=%s",
            request.url.path,
            type(exc).__name__,
        )
        raise AuthenticationError(
            "Invalid or expired token"
        ) from exc

    return payload
