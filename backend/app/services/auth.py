from datetime import datetime, timezone
from sqlmodel import select
from app.core.security import token_hash, verify_password
from app.exceptions.errors import AuthenticationError
from app.models.models import TokenBlacklist, User
from app.services.rbac import provision_user


async def authenticate(db, username: str, password: str) -> User:
    user = await provision_user(db, username, password=password)
    if not user.is_active or not user.local_login_enabled:
        raise AuthenticationError('账号已停用或不支持密码登录')
    if not verify_password(password, user.password_hash):
        raise AuthenticationError('用户名或密码错误')
    return user


async def revoked(db, token: str) -> bool:
    return (await db.execute(select(TokenBlacklist.id).where(
        TokenBlacklist.token_hash == token_hash(token)))).first() is not None


async def revoke(db, token: str, payload: dict, user_id: int | None = None):
    if await revoked(db, token):
        return
    db.add(TokenBlacklist(token_hash=token_hash(token), user_id=user_id or int(payload['sub']),
                          expires_at=datetime.fromtimestamp(payload['exp'], timezone.utc).replace(tzinfo=None)))
    await db.commit()
