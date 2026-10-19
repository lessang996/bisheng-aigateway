import logging
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.security import decode_token
from app.db.session import get_db
from app.exceptions.errors import AuthenticationError, AuthorizationError
from app.models.models import User
from app.services.auth import revoked
from app.services.rbac import access_for, provision_user

logger = logging.getLogger(__name__)


def extract_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get('Authorization', '').strip().partition(' ')
    return value.strip() or None if scheme.lower() == 'bearer' else None


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    token = extract_token(request)
    if not token:
        raise AuthenticationError('Authentication required')
    payload = decode_token(token, expected_type='access')
    if await revoked(db, token):
        raise AuthenticationError('Token revoked')
    if payload.get('type'):
        try:
            account = await db.get(User, int(payload['sub']))
        except (ValueError, TypeError, KeyError):
            account = None
        if account is None:
            raise AuthenticationError('User does not exist')
    else:
        username = payload.get('userNo')
        if not isinstance(username, str) or not username.strip() or len(username) > 100:
            raise AuthenticationError('Invalid userNo')
        department = payload.get('org')
        if department is not None and (not isinstance(department, str) or len(department) > 100):
            raise AuthenticationError('Invalid org')
        account = await provision_user(db, username, department=department or None)
        if not account.department and department:
            account.department = department
            db.add(account)
            await db.commit()
    if not account.is_active:
        raise AuthenticationError('User disabled')
    request.state.access = await access_for(db, account)
    return {**payload, 'userNo': account.username, 'org': account.department,
            'local_user_id': account.id}


def require_permission(code: str):
    async def dependency(request: Request, user: dict = Depends(current_user)):
        if not request.state.access.allows(code):
            raise AuthorizationError('没有访问此资源的权限')
        return user
    return dependency
