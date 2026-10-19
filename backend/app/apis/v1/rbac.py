import json
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.apis.deps import current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import User, Role, Permission, Menu, UserRole, RolePermission, RoleMenu, AuditLog
from app.schemas.rbac import UserWrite, RoleWrite, PermissionWrite, MenuWrite
from app.services.rbac import PAGE_PERMISSIONS, assign_default_role, public_user

router = APIRouter(prefix='/api/admin', tags=['rbac'])
Resource = Literal['users', 'roles', 'permissions', 'menus']
MODELS = {'users': User, 'roles': Role, 'permissions': Permission, 'menus': Menu}
SCHEMAS = {'users': UserWrite, 'roles': RoleWrite, 'permissions': PermissionWrite, 'menus': MenuWrite}


def authorize(request, resource):
    if not request.state.access.allows(f'{resource}:manage'):
        raise HTTPException(403, '没有管理权限')


async def lock_admin(db):
    # Serialize changes affecting the last administrator on MySQL.
    await db.execute(select(Role).where(Role.code == 'admin').with_for_update())


async def ensure_admin(db):
    await db.flush()
    # A locking read sees the latest committed grants even under MySQL's
    # REPEATABLE READ when authentication has already opened a read snapshot.
    active = (await db.execute(select(User.id).join(UserRole).join(Role).where(
        User.is_active == True, Role.code == 'admin', Role.is_active == True).with_for_update())).first()
    if active is None:
        raise HTTPException(409, '必须保留至少一个有效管理员')


async def replace_links(db, link, owner_field, owner_id, target_field, target_model, ids):
    ids = set(ids)
    found = set((await db.execute(select(target_model.id).where(target_model.id.in_(ids)))).scalars())
    if ids != found:
        raise HTTPException(422, '关联的角色、权限或菜单不存在')
    await db.execute(delete(link).where(getattr(link, owner_field) == owner_id))
    for target_id in ids:
        db.add(link(**{owner_field: owner_id, target_field: target_id}))


async def serialize(db, resource, item):
    result = public_user(item) if resource == 'users' else item.model_dump()
    if resource == 'users':
        result['role_ids'] = list((await db.execute(select(UserRole.role_id).where(UserRole.user_id == item.id))).scalars())
    if resource == 'roles':
        result['permission_ids'] = list((await db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == item.id))).scalars())
        result['menu_ids'] = list((await db.execute(select(RoleMenu.menu_id).where(RoleMenu.role_id == item.id))).scalars())
    return result


@router.get('/rbac-options')
async def options(request: Request, db=Depends(get_db), user=Depends(current_user)):
    if not any(request.state.access.allows(f'{r}:manage') for r in MODELS):
        raise HTTPException(403, '没有管理权限')
    return {'pages': [{'path': p, 'permission_code': v[0], 'name': v[1]} for p, v in PAGE_PERMISSIONS.items()],
            'roles': [r.model_dump() for r in (await db.execute(select(Role))).scalars()],
            'permissions': [p.model_dump() for p in (await db.execute(select(Permission))).scalars()],
            'menus': [m.model_dump() for m in (await db.execute(select(Menu).order_by(Menu.sort_order, Menu.id))).scalars()]}


@router.get('/{resource}')
async def listing(resource: Resource, request: Request, q: str = '', page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100), db=Depends(get_db), user=Depends(current_user)):
    authorize(request, resource)
    model = MODELS[resource]
    statement = select(model)
    if q:
        statement = statement.where((model.username if resource == 'users' else model.name).contains(q, autoescape=True))
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    rows = (await db.execute(statement.order_by(model.id).offset((page-1)*page_size).limit(page_size))).scalars()
    return {'items': [await serialize(db, resource, row) for row in rows], 'total': total}


async def validate_menu(db, values, item_id):
    kind, path = values['kind'], values['path']
    if kind == 'page':
        if path not in PAGE_PERMISSIONS:
            raise HTTPException(422, '请选择已注册的页面')
        values['permission_code'] = PAGE_PERMISSIONS[path][0]
    elif kind == 'external':
        parsed = urlparse(path or '')
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(422, '外链必须是有效的 HTTP/HTTPS 地址')
    elif path:
        raise HTTPException(422, '目录不能配置页面地址')
    if values['permission_code'] and not (await db.execute(select(Permission.id).where(Permission.code == values['permission_code']))).first():
        raise HTTPException(422, '权限编码不存在')
    parent = values['parent_id']
    seen = {item_id} if item_id else set()
    while parent:
        if parent in seen:
            raise HTTPException(422, '菜单不能循环嵌套')
        seen.add(parent)
        row = await db.get(Menu, parent)
        if row is None or row.kind != 'directory':
            raise HTTPException(422, '父菜单必须是存在的目录')
        parent = row.parent_id
    if item_id and kind != 'directory' and (await db.execute(select(Menu.id).where(Menu.parent_id == item_id))).first():
        raise HTTPException(422, '请先移出子菜单再修改目录类型')


async def save(resource, payload, request, db, item_id=None):
    authorize(request, resource)
    try:
        parsed = SCHEMAS[resource].model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json(include_input=False))) from exc
    values = parsed.model_dump(exclude_unset=resource == 'users')
    model = MODELS[resource]
    try:
        await lock_admin(db)
        item = await db.get(model, item_id) if item_id else None
        if item_id and item is None:
            raise HTTPException(404, '记录不存在')
        if resource == 'users':
            roles = values.pop('role_ids', None)
            password = values.pop('password', None)
            if item:
                if values.get('username', item.username) != item.username:
                    raise HTTPException(422, '用户名作为外部身份标识不可修改')
                if values.get('local_login_enabled') and not item.local_login_enabled and not password:
                    raise HTTPException(422, '启用密码登录时必须设置密码')
                if any(values.get(k) is None for k in ('username', 'email') if k in values):
                    raise HTTPException(422, '用户名和邮箱不可为空')
            else:
                if not values.get('username') or not values['username'].strip():
                    raise HTTPException(422, '请输入用户名')
                if not values.get('email'):
                    values['email'] = f"{values['username']}@local"
                if values.get('local_login_enabled', True) and not password:
                    raise HTTPException(422, '启用密码登录时必须设置密码')
                values['password_hash'] = '!'
            if password:
                values['password_hash'] = hash_password(password)
        elif resource == 'roles':
            permissions, menus = values.pop('permission_ids'), values.pop('menu_ids')
            if item and item.is_builtin and values['code'] != item.code:
                raise HTTPException(422, '内置角色编码不可修改')
            if not item and values['code'] in {'admin', 'user'}:
                raise HTTPException(422, '保留的角色编码')
        elif resource == 'permissions':
            if item and item.code != values['code']:
                referenced = (await db.execute(select(Menu.id).where(Menu.permission_code == item.code))).first()
                if item.is_builtin or referenced:
                    raise HTTPException(422, '内置或被菜单引用的权限编码不可修改')
        else:
            await validate_menu(db, values, item_id)
        if item is None:
            item = model(**values)
        else:
            for key, value in values.items():
                setattr(item, key, value)
        db.add(item)
        await db.flush()
        if resource == 'users':
            if roles is not None:
                await replace_links(db, UserRole, 'user_id', item.id, 'role_id', Role, roles)
            elif not item_id:
                await assign_default_role(db, item.id)
        if resource == 'roles':
            await replace_links(db, RolePermission, 'role_id', item.id, 'permission_id', Permission, permissions)
            await replace_links(db, RoleMenu, 'role_id', item.id, 'menu_id', Menu, menus)
        await ensure_admin(db)
        db.add(AuditLog(user_id=request.state.access.user.id, action='update' if item_id else 'create',
                        resource=f'{resource}/{item.id}', details=json.dumps({'fields': sorted(payload)}, ensure_ascii=False),
                        ip_address=request.client.host if request.client else ''))
        await db.commit()
        return await serialize(db, resource, item)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, '编码、用户名、邮箱或工号已存在') from exc
    except Exception:
        await db.rollback()
        raise


@router.post('/{resource}')
async def create(resource: Resource, payload: dict, request: Request, db=Depends(get_db), user=Depends(current_user)):
    return await save(resource, payload, request, db)


@router.put('/{resource}/{item_id}')
async def update(resource: Resource, item_id: int, payload: dict, request: Request, db=Depends(get_db), user=Depends(current_user)):
    return await save(resource, payload, request, db, item_id)


@router.delete('/{resource}/{item_id}')
async def remove(resource: Resource, item_id: int, request: Request, db=Depends(get_db), user=Depends(current_user)):
    authorize(request, resource)
    try:
        await lock_admin(db)
        item = await db.get(MODELS[resource], item_id)
        if item is None:
            raise HTTPException(404, '记录不存在')
        if resource == 'users':
            item.is_active = False
            db.add(item)
        else:
            if getattr(item, 'is_builtin', False):
                raise HTTPException(409, '内置角色和权限不能删除')
            if resource == 'roles':
                if (await db.execute(select(UserRole).where(UserRole.role_id == item_id))).first():
                    raise HTTPException(409, '请先解除用户与该角色的关联')
                for link in (RoleMenu, RolePermission):
                    await db.execute(delete(link).where(link.role_id == item_id))
            if resource == 'menus':
                if (await db.execute(select(Menu.id).where(Menu.parent_id == item_id))).first():
                    raise HTTPException(409, '请先移出子菜单')
                await db.execute(delete(RoleMenu).where(RoleMenu.menu_id == item_id))
            if resource == 'permissions':
                if (await db.execute(select(Menu.id).where(Menu.permission_code == item.code))).first():
                    raise HTTPException(409, '权限仍被菜单引用')
                await db.execute(delete(RolePermission).where(RolePermission.permission_id == item_id))
            await db.delete(item)
        await ensure_admin(db)
        db.add(AuditLog(user_id=request.state.access.user.id, action='disable' if resource == 'users' else 'delete', resource=f'{resource}/{item_id}'))
        await db.commit()
        return {'success': True}
    except Exception:
        await db.rollback()
        raise
