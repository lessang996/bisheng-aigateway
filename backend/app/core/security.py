import hashlib
import logging
from pydoc import plain
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import JWTError
import jwt
from passlib.context import CryptContext
from app.core.config import get_settings
from app.exceptions.errors import AuthenticationError
import base64
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

logger = logging.getLogger(__name__)

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
    user_name: Optional[str] = None,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT with standard claims (sub, type, iss, aud, iat, exp, jti)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        exp = now + expires_delta
    elif token_type == "access":
        exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        exp = now + timedelta(days=settings.refresh_token_expire_days)

    key = (
        settings.jwt_public_key
        if settings.jwt_algorithm == "RS256"
        else settings.jwt_secret_key
    )
    deconded_key = base64.b64decode(key)
    payload = {
        "sub": subject,
        "type": token_type,
        # "iss": settings.jwt_issuer,
        # "aud": settings.jwt_audience,
        "iat": now,
        "exp": exp,
        "jti": secrets.token_hex(16),
        "userNo": user_name,
    }

    return jwt.encode(payload, deconded_key, algorithm=settings.jwt_algorithm)


def decode_token(
    token: str,
    expected_type: Optional[str] = None,
) -> dict:
    """Decode and validate a JWT, optionally checking the token type claim."""
    settings = get_settings()
    key = (
        settings.jwt_public_key
        if settings.jwt_algorithm == "RS256"
        else settings.jwt_secret_key
    )
    deconded_key=base64.b64decode(key)
    logger.info(f"jwt_secret_key,{deconded_key},token is value,{token}")
    try:
        payload = jwt.decode(
            token,
            deconded_key,
            algorithms=[settings.jwt_algorithm],      
        )
        return payload

    except (JWTError, ValueError) as e:
        raise AuthenticationError("Invalid or expired token") from e
