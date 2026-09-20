import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.deps import extract_token
from app.core.security import create_token, decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError
from app.schemas import LoginRequest, TokenResponse, VerifyResponse
from app.services.auth import authenticate, revoke, revoked

router = APIRouter(prefix="/auth", tags=["auth"])
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
    return {
        "access_token": create_token(payload["sub"], payload.get("username")),
        "refresh_token": create_token(payload["sub"], payload.get("username"), "refresh"),
        "expires_in": 1800,
    }


@router.get("/verify", response_model=VerifyResponse)
async def verify(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = extract_token(request)
    if not token or await revoked(db, token):
        raise AuthenticationError("Token revoked")

    payload = decode_token(token, "access")
    return {
        "valid": True,
        "subject": payload["sub"],
        "expires_at": datetime.fromtimestamp(payload["exp"], timezone.utc),
    }


@router.post("/revoke")
async def revoke_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = extract_token(request)
    if not token:
        raise AuthenticationError("Authentication required")
    payload = decode_token(token, "access")
    await revoke(db, token, payload)
    return {"message": "revoked"}
