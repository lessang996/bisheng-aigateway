from datetime import datetime, timezone
from typing import Optional
from aiomysql import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.security import hash_password, token_hash, verify_password
from app.models.models import TokenBlacklist, User


async def authenticate(
    db: AsyncSession,
    username: str,
    password: str,
) -> Optional[User]:
    """
    验证用户名和密码。

    - 用户存在：校验密码，正确则返回用户
    - 用户不存在：自动创建用户并返回
    """

    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    # 用户不存在，自动创建
    if user is None:
        user = User(
            username=username,
            email=f"{username}@local",
            password_hash=hash_password(password),
        )

        try:
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user

        except IntegrityError:
            # 防止并发请求同时创建相同 username
            await db.rollback()

            result = await db.execute(
                select(User).where(User.username == username)
            )
            user = result.scalar_one_or_none()

            if user is None:
                return None

            # 已经被其他请求创建，继续校验密码
            if not verify_password(password, user.password_hash):
                return None

            return user

    # 用户存在，校验密码
    if not verify_password(password, user.password_hash):
        return None

    return user

async def revoked(db: AsyncSession, token: str) -> bool:
    """检查令牌是否已被吊销。"""
    result = await db.execute(
        select(TokenBlacklist.id).where(TokenBlacklist.token_hash == token_hash(token))
    )
    return result.scalar_one_or_none() is not None

async def revoke(db: AsyncSession, token: str, payload: dict) -> None:
    """将令牌加入黑名单以吊销。"""
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)

    db.add(
        TokenBlacklist(
            token_hash=token_hash(token),
            user_id=int(payload["sub"]),
            expires_at=exp,
        )
    )
    await db.commit()
