from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.models import User
from app.core.security import hash_password

PASSWORD = "1234"


async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def update_principal_id(
    db: AsyncSession,
    username: str,
    principal_id: int,
) -> Optional[User]:
    user = await get_by_username(db, username)

    if user is None:
        user = User(
            username=username,
            email=f"{username}@local",
            password_hash=hash_password(PASSWORD),
            principal_id=principal_id,
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

    user.principal_id = principal_id
    await db.commit()
    await db.refresh(user)
    return user