import logging
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError

from typing import Optional



logger = logging.getLogger(__name__)


def extract_token(request: Request) -> Optional[str]:
    """
    提取 JWT Token。

    支持：

    1. Authorization: Bearer <token>
    2. Authorization: <token>
    3. ?token=<token>

    优先级：
        Bearer Header
        ↓
        Authorization Header
        ↓
        Query Parameter
    """

    auth_header = request.headers.get("Authorization", "").strip()

    if auth_header:
        # Authorization: Bearer <token>
        scheme, _, credentials = auth_header.partition(" ")

        if scheme.lower() == "bearer":
            token = credentials.strip()

            if token:
                return token

        # Authorization: <token>
        # 没有 Bearer 前缀时，直接把整个 Header 当 Token
        if " " not in auth_header:
            return auth_header

    # ?token=<token>
    token = request.query_params.get("token")

    if token:
        token = token.strip()

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
    except Exception as exc:
        logger.warning(
            "JWT authentication failed path=%s error=%s",
            request.url.path,
            type(exc).__name__,
        )
        raise AuthenticationError(
            "Invalid or expired token"
        ) from exc
    
    return payload