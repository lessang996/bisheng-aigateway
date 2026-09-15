from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.repositories import user as user_repository


async def get_principal(
    db: AsyncSession,
    username: str,
) -> Optional[User]:
    """获取用户主体信息"""
    return await user_repository.get_by_username(db, username)


async def update_principal_id(
    db: AsyncSession,
    username: str,
    principal_id: int,
) -> Optional[User]:
    """
    通过 username 查找用户并更新 principal_id

    Args:
        db: 异步数据库会话
        username: 用户名
        principal_id: 新的负责人ID

    Returns:
        更新后的 User 对象，未找到则返回 None
    """
    return await user_repository.update_principal_id(db, username, principal_id)


