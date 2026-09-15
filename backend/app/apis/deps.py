from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError
from app.services.auth import revoked


def extract_token(request: Request) -> Optional[str]:
    """Extract a bearer token from the header or query parameters."""
    auth_header = request.headers.get("Authorization", "")
    return request.query_params.get("token") or auth_header.removeprefix("Bearer ").strip()


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate the current access token and return its claims."""
    token = extract_token(request)
    if not token or await revoked(db, token):
        raise AuthenticationError("Authentication required")
    return decode_token(token, "access")
