import pytest
from sqlmodel import select

from app.init import admin
from app.core.security import verify_password
from app.models.models import AuditLog, Role, User, UserRole
from test_rbac_stats import context


@pytest.mark.asyncio
async def test_create_admin_and_repeat_preserves_password(context, monkeypatch):
    monkeypatch.setattr(admin, 'SessionLocal', context.db)
    monkeypatch.setenv('BOOTSTRAP_USER_PASSWORD', 'test-bootstrap-password')
    assert await admin.initialize_admin('new-admin') is True
    monkeypatch.setenv('BOOTSTRAP_USER_PASSWORD', 'different-password')
    assert await admin.initialize_admin('new-admin') is False
    async with context.db() as db:
        account = (await db.execute(select(User).where(User.username == 'new-admin'))).scalar_one()
        assert verify_password('test-bootstrap-password', account.password_hash)
        grants = list((await db.execute(select(UserRole).join(Role).where(
            UserRole.user_id == account.id, Role.code == 'admin'))).scalars())
        assert len(grants) == 1
        audits = list((await db.execute(select(AuditLog).where(
            AuditLog.user_id == account.id, AuditLog.action == 'initialize_admin'))).scalars())
        assert len(audits) == 1


@pytest.mark.asyncio
async def test_missing_password_and_disabled_accounts(context, monkeypatch):
    monkeypatch.setattr(admin, 'SessionLocal', context.db)
    monkeypatch.delenv('BOOTSTRAP_USER_PASSWORD', raising=False)
    with pytest.raises(ValueError, match='BOOTSTRAP_USER_PASSWORD'):
        await admin.initialize_admin('new-admin')
    assert await admin.initialize_admin('alice') is False
    async with context.db() as db:
        bob = await db.get(User, context.ids['bob'])
        bob.is_active = False
        db.add(bob)
        await db.commit()
    with pytest.raises(ValueError, match='账号已停用'):
        await admin.initialize_admin('bob')
