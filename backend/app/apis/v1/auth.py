import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.deps import extract_token, current_user
from app.models.models import User
from app.services.rbac import public_user
from app.core.security import create_token, decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError
from app.schemas import LoginRequest, TokenResponse, VerifyResponse
from app.services.auth import authenticate, revoke, revoked

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await authenticate(db, data.username, data.password)
    return {
        "access_token": create_token(str(user.id), user.username),
        "refresh_token": create_token(str(user.id), user.username, "refresh"),
        "expires_in": 1800,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = extract_token(request)
    if not token or await revoked(db, token):
        raise AuthenticationError("Invalid refresh token")

    payload = decode_token(token, "refresh")
    try:
        subject = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid refresh subject") from exc
    account = await db.get(User, subject)
    if account is None or not account.is_active or not account.local_login_enabled:
        raise AuthenticationError("User disabled")
    return {
        "access_token": create_token(payload["sub"], account.username),
        "refresh_token": create_token(payload["sub"], account.username, "refresh"),
        "expires_in": 1800,
    }


@router.get("/verify", response_model=VerifyResponse)
async def verify(
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = extract_token(request)
    if not token or await revoked(db, token):
        raise AuthenticationError("Token revoked")

    payload = decode_token(token, "access")
    return {
        "valid": True,
        "subject": str(user["local_user_id"]),
        "expires_at": datetime.fromtimestamp(payload["exp"], timezone.utc),
    }


@router.post("/revoke")
async def revoke_token(
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = extract_token(request)
    if not token:
        raise AuthenticationError("Authentication required")
    payload = decode_token(token, "access")
    await revoke(db, token, payload, user["local_user_id"])
    return {"message": "revoked"}


@router.get("/me")
async def me(request: Request, user: dict = Depends(current_user)):
    access = request.state.access
    return {"user": public_user(access.user), "roles": [r.model_dump() for r in access.roles],
            "permissions": sorted(access.permissions), "is_admin": access.admin,
            "menus": [m.model_dump() for m in access.menus]}
