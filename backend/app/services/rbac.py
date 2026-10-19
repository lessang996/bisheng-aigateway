from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.models import User, Role, Permission, Menu, UserRole, RolePermission, RoleMenu

# This registry is also returned to the menu editor; paths never execute code.
PAGE_PERMISSIONS = {
    '/dashboard': ('dashboard:view', '工作台'),
    '/agents': ('agent:view', 'Agent 管理'),
    '/conversations': ('conversation:view', '对话中心'),
    '/reports': ('report:use', '报告中心'),
    '/stats': ('stats:view', '使用统计'),
    '/knowledge': ('knowledge:view', '知识库'),
    '/users': ('users:manage', '用户管理'),
    '/roles': ('roles:manage', '角色管理'),
    '/permissions': ('permissions:manage', '权限管理'),
    '/menus': ('menus:manage', '菜单管理'),
    '/system/health': ('system:view', '系统健康'),
    '/system/logs': ('logs:view', '系统日志'),
    '/system/settings': ('system:manage', '系统设置'),
}
DEFAULT_PERMISSIONS = {'dashboard:view', 'report:use', 'conversation:view', 'stats:view'}


async def seed_rbac(db, *, administrator: str | None = None):
    """Idempotent explicit setup. Existing grants/settings are never replaced."""
    admin_user = None
    if administrator:
        admin_user = (await db.execute(select(User).where(User.username == administrator))).scalar_one_or_none()
        if admin_user is None or admin_user.username != administrator:
            raise ValueError(f'管理员账号 {administrator} 不存在，请先创建账号后重跑初始化')
        if not admin_user.is_active:
            raise ValueError('管理员账号已停用，请先启用后重跑初始化')
    roles = {r.code: r for r in (await db.execute(select(Role))).scalars()}
    new_regular = 'user' not in roles
    for code, name, scope in [('admin', '管理员', 'all'), ('user', '普通用户', 'self')]:
        if code not in roles:
            roles[code] = Role(code=code, name=name, data_scope=scope, is_builtin=True)
            db.add(roles[code])
    await db.flush()
    permissions = {p.code: p for p in (await db.execute(select(Permission))).scalars()}
    for code, name in PAGE_PERMISSIONS.values():
        if code not in permissions:
            permissions[code] = Permission(code=code, name=name, is_builtin=True)
            db.add(permissions[code])
    await db.flush()
    menus = {m.path: m for m in (await db.execute(select(Menu))).scalars() if m.kind == 'page'}
    for order, (path, (code, name)) in enumerate(PAGE_PERMISSIONS.items()):
        if new_regular and path not in menus:
            menus[path] = Menu(code=path.strip('/').replace('/', '-'), name=name, path=path,
                               permission_code=code, sort_order=order * 10)
            db.add(menus[path])
    await db.flush()
    if new_regular:
        for code in DEFAULT_PERMISSIONS:
            db.add(RolePermission(role_id=roles['user'].id, permission_id=permissions[code].id))
        for menu in menus.values():
            if menu.permission_code in DEFAULT_PERMISSIONS:
                db.add(RoleMenu(role_id=roles['user'].id, menu_id=menu.id))
    if new_regular:
        for user in (await db.execute(select(User))).scalars():
            if not (await db.execute(select(UserRole).where(UserRole.user_id == user.id))).first():
                db.add(UserRole(user_id=user.id, role_id=roles['user'].id))
    if admin_user and not await db.get(UserRole, (admin_user.id, roles['admin'].id)):
        db.add(UserRole(user_id=admin_user.id, role_id=roles['admin'].id))
    await db.commit()


async def assign_default_role(db, user_id: int):
    role = (await db.execute(select(Role).where(Role.code == 'user'))).scalar_one_or_none()
    if role is None:
        raise HTTPException(503, '权限体系尚未初始化，请先执行初始化命令')
    db.add(UserRole(user_id=user_id, role_id=role.id))


async def provision_user(db, username: str, *, password: str | None = None, department: str | None = None):
    from app.core.security import hash_password
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user:
        if user.username != username:
            raise HTTPException(409, "用户名大小写与已有账号不一致")
        return user
    user = User(username=username, email=f'{username}@local', department=department,
                password_hash=hash_password(password) if password is not None else '!',
                local_login_enabled=password is not None)
    try:
        db.add(user)
        await db.flush()
        await assign_default_role(db, user.id)
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if user is None or user.username != username:
            raise HTTPException(409, '用户名或邮箱冲突')
    return user


@dataclass
class Access:
    user: User
    roles: list[Role]
    permissions: set[str]
    scopes: set[str]
    menus: list[Menu]

    @property
    def admin(self):
        return any(r.code == 'admin' for r in self.roles)

    def allows(self, permission: str):
        return self.admin or permission in self.permissions

    def constrain(self, statement, model):
        if self.admin or 'all' in self.scopes:
            return statement
        conditions = [model.local_user_id == self.user.id]
        if 'department' in self.scopes and self.user.department:
            conditions.append(model.user_department == self.user.department)
        return statement.where(or_(*conditions))


async def access_for(db, user: User) -> Access:
    roles = list((await db.execute(select(Role).join(UserRole).where(
        UserRole.user_id == user.id, Role.is_active == True))).scalars())
    role_ids = [r.id for r in roles]
    permissions = set((await db.execute(select(Permission.code).join(RolePermission).where(
        RolePermission.role_id.in_(role_ids)))).scalars())
    admin = any(r.code == 'admin' for r in roles)
    all_menus = list((await db.execute(select(Menu).order_by(Menu.sort_order, Menu.id))).scalars())
    granted = set((await db.execute(select(RoleMenu.menu_id).where(RoleMenu.role_id.in_(role_ids)))).scalars())
    by_id = {m.id: m for m in all_menus}
    def enabled(menu):
        seen = set()
        while menu:
            if not menu.is_active or menu.id in seen:
                return False
            seen.add(menu.id)
            menu = by_id.get(menu.parent_id)
        return True
    visible = {m.id for m in all_menus if enabled(m) and (admin or (
        m.id in granted and (not m.permission_code or m.permission_code in permissions)))}
    for menu_id in list(visible):
        parent = by_id[menu_id].parent_id
        while parent in by_id:
            visible.add(parent)
            parent = by_id[parent].parent_id
    return Access(user, roles, permissions, {r.data_scope for r in roles},
                  [m for m in all_menus if m.id in visible])


def public_user(user: User) -> dict[str, Any]:
    return user.model_dump(exclude={'password_hash', 'principal_id'})
