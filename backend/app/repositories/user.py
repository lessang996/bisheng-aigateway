from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.models import User


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
        return None
    user.principal_id = principal_id
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
