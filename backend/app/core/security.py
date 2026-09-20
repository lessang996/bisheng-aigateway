import base64
import binascii
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import get_settings
from app.exceptions.errors import AuthenticationError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _decode_hs256_secret(value: str) -> bytes:
    """Decode and validate the externally supplied HS256 secret."""
    if not value:
        raise ValueError("JWT_SECRET_KEY is required for HS256")
    try:
        secret = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("JWT_SECRET_KEY must be valid base64") from exc
    if len(secret) < 32:
        raise ValueError("JWT_SECRET_KEY must decode to at least 32 bytes")
    return secret


def _signing_key() -> bytes | str:
    settings = get_settings()
    if settings.jwt_algorithm == "HS256":
        return _decode_hs256_secret(settings.jwt_secret_key)
    if not settings.jwt_private_key.strip():
        raise ValueError("JWT_PRIVATE_KEY is required for RS256 token signing")
    return settings.jwt_private_key


def _verification_key() -> bytes | str:
    settings = get_settings()
    if settings.jwt_algorithm == "HS256":
        return _decode_hs256_secret(settings.jwt_secret_key)
    if not settings.jwt_public_key.strip():
        raise ValueError("JWT_PUBLIC_KEY is required for RS256 token verification")
    return settings.jwt_public_key

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]  # 按字节截断到72
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))


def token_hash(token: str) -> str:
    """Generate a SHA-256 hex digest of the given token string."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(
    subject: str,
    user_name: str | None = None,
    token_type: str = "access",
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT with standard claims (sub, type, iss, aud, iat, exp, jti)."""
    if token_type not in {"access", "refresh"}:
        raise ValueError("token_type must be access or refresh")

    settings = get_settings()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        exp = now + expires_delta
    elif token_type == "access":
        exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        exp = now + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": subject,
        "type": token_type,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": exp,
        "jti": secrets.token_hex(16),
        "userNo": user_name,
    }

    return jwt.encode(payload, _signing_key(), algorithm=settings.jwt_algorithm)


def decode_token(
    token: str,
    expected_type: str | None = None,
) -> dict:
    """Decode and validate a JWT, optionally checking the token type claim."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _verification_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "type", "iss", "aud", "iat", "exp", "jti"]},
        )
        if expected_type is not None and payload.get("type") != expected_type:
            raise AuthenticationError("Invalid token type")
        return payload

    except AuthenticationError:
        raise
    except (InvalidTokenError, ValueError, TypeError) as e:
        raise AuthenticationError("Invalid or expired token") from e
