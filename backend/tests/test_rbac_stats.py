import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, select
from sqlalchemy import delete

from app.apis.router import api_router
from app.core.config import get_settings
from app.core.security import create_token, hash_password
from app.db.session import get_db
from app.exceptions.errors import GatewayError
from app.exceptions.handlers import gateway_exception_handler
from app.models.models import User, Role, UserRole, RolePermission, Permission, ChatSession, ChatMessage, Menu
from app.services.rbac import seed_rbac, provision_user


@pytest_asyncio.fixture
async def context(tmp_path, monkeypatch):
    monkeypatch.setenv('JWT_ALGORITHM', 'HS256')
    monkeypatch.setenv('JWT_SECRET_KEY', base64.b64encode(b'test-secret-at-least-32-bytes-long!!').decode())
    monkeypatch.setenv('JWT_ISSUER', 'bisheng-gateway')
    monkeypatch.setenv('JWT_AUDIENCE', 'bisheng-client')
    get_settings.cache_clear()
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "test.db"}')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with factory() as db:
        admin = User(username='cqbank', email='admin@test', password_hash=hash_password('password123'), department='A')
        db.add(admin)
        await db.commit()
        await seed_rbac(db, administrator='cqbank')
        alice = await provision_user(db, 'alice', password='password123', department='A')
        bob = await provision_user(db, 'bob', password='password123', department='B')
        ids = {'cqbank': admin.id, 'alice': alice.id, 'bob': bob.id}
    app = FastAPI()
    app.include_router(api_router)
    app.add_exception_handler(GatewayError, gateway_exception_handler)
    async def database():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    import app.services.report_usage as usage_module
    monkeypatch.setattr(usage_module, 'SessionLocal', factory)
    def headers(name):
        return {'Authorization': 'Bearer ' + create_token(str(ids[name]), name)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield SimpleNamespace(db=factory, client=client, ids=ids, headers=headers, app=app)
    await engine.dispose()
    get_settings.cache_clear()


async def insert_request(ctx, username, *, cache='miss', state='success', at=None, duration=100, answer_count=1):
    async with ctx.db() as db:
        account = await db.get(User, ctx.ids[username])
        session = ChatSession(user_id=username, local_user_id=account.id, user_department=account.department)
        db.add(session)
        await db.flush()
        question = ChatMessage(session_id=session.id, user_id=username, local_user_id=account.id,
                               user_department=account.department, role='user', content='question',
                               business_type='industry_report', cache_status=cache, execution_status=state,
                               created_at=at or datetime.utcnow(), duration_ms=duration)
        db.add(question)
        await db.flush()
        for _ in range(answer_count):
            db.add(ChatMessage(session_id=session.id, parent_id=question.id, role='redis_cache' if cache=='hit' else 'assistant', category='answer', content='answer'))
        await db.commit()
        return question.id


@pytest.mark.asyncio
async def test_defaults_and_external_autoprovision(context):
    ctx = context
    response = await ctx.client.get('/api/auth/me', headers=ctx.headers('alice'))
    assert response.status_code == 200
    assert response.json()['is_admin'] is False
    assert {m['path'] for m in response.json()['menus']} == {'/dashboard','/reports','/conversations','/stats'}
    token = jwt.encode({'userNo':'external', 'org':'C', 'exp':datetime.now(timezone.utc)+timedelta(hours=1)}, base64.b64decode(get_settings().jwt_secret_key), algorithm='HS256')
    response = await ctx.client.get('/api/auth/me', headers={'Authorization':f'Bearer {token}'})
    assert response.status_code == 200
    assert response.json()['user']['department'] == 'C'
    assert response.json()['user']['local_login_enabled'] is False
    assert (await ctx.client.post('/api/auth/login',json={'username':'external','password':'password123'})).status_code == 401
    response = await ctx.client.post('/api/auth/login',json={'username':'new-local','password':'password123'})
    assert response.status_code == 200
    assert (await ctx.client.get('/api/admin/users',headers={'Authorization':'Bearer '+response.json()['access_token']})).status_code == 403


@pytest.mark.asyncio
async def test_admin_protection_and_revocation(context):
    ctx=context
    admin_headers=ctx.headers('cqbank')
    response=await ctx.client.put(f'/api/admin/users/{ctx.ids["cqbank"]}',json={'is_active':False},headers=admin_headers)
    assert response.status_code==409
    response=await ctx.client.put(f'/api/admin/users/{ctx.ids["cqbank"]}',json={'role_ids':[]},headers=admin_headers)
    assert response.status_code==409
    response=await ctx.client.delete(f'/api/admin/users/{ctx.ids["cqbank"]}',headers=admin_headers)
    assert response.status_code==409
    assert (await ctx.client.get('/api/auth/me',headers=admin_headers)).status_code==200
    headers=ctx.headers('alice')
    assert (await ctx.client.post('/api/auth/revoke',headers=headers)).status_code==200
    assert (await ctx.client.get('/api/auth/me',headers=headers)).status_code==401
    assert (await ctx.client.put(f'/api/admin/users/{ctx.ids["bob"]}',json={'is_active':False},headers=admin_headers)).status_code==200
    assert (await ctx.client.get('/api/auth/me',headers=ctx.headers('bob'))).status_code==401


@pytest.mark.asyncio
async def test_statistics_scope_aggregation_and_detail(context):
    ctx=context
    own=await insert_request(ctx,'alice',cache='hit',answer_count=2)
    other=await insert_request(ctx,'bob',cache='error',state='failed',duration=200)
    await insert_request(ctx,'alice',cache='unknown',state='unknown',duration=None,answer_count=0)
    headers=ctx.headers('alice')
    result=(await ctx.client.get('/api/stats/industry-report/overview',headers=headers)).json()
    assert result['total']==2 and result['cache_hits']==1 and result['cache_queries']==1 and result['cache_rate']==100
    assert result['avg_duration_ms']==100 and result['unknown']==1
    assert (await ctx.client.get(f'/api/stats/industry-report/{other}',headers=headers)).status_code==404
    assert len((await ctx.client.get(f'/api/stats/industry-report/{own}',headers=headers)).json()['answers'])==2
    for dim in ['user','department','day','month','cache']:
        result=(await ctx.client.get(f'/api/stats/industry-report/groups?dimension={dim}',headers=headers)).json()
        assert sum(r['total'] for r in result['items'])==2
    response=(await ctx.client.get('/api/stats/industry-report/details?page_size=1',headers=ctx.headers('cqbank'))).json()
    assert response['total']==3 and len(response['items'])==1
    assert (await ctx.client.get('/api/stats/industry-report/overview?user_id=bob',headers=headers)).json()['total']==0


@pytest.mark.asyncio
async def test_department_scope_and_multirole_union(context):
    ctx=context
    await insert_request(ctx,'alice'); await insert_request(ctx,'cqbank'); await insert_request(ctx,'bob')
    async with ctx.db() as db:
        role=Role(code='department-reader',name='部门读者',data_scope='department')
        db.add(role); await db.flush()
        db.add(UserRole(user_id=ctx.ids['alice'],role_id=role.id)); await db.commit()
    assert (await ctx.client.get('/api/stats/industry-report',headers=ctx.headers('alice'))).json()['total']==2
    async with ctx.db() as db:
        alice=await db.get(User,ctx.ids['alice']); alice.department=None; db.add(alice)
        bob=await db.get(User,ctx.ids['bob']); bob.department=None; db.add(bob); await db.commit()
    await insert_request(ctx,'bob')
    assert (await ctx.client.get('/api/stats/industry-report',headers=ctx.headers('alice'))).json()['total']==1


@pytest.mark.asyncio
async def test_beijing_date_boundary(context):
    ctx=context
    await insert_request(ctx,'alice',at=datetime(2026,10,18,15,59,59))
    await insert_request(ctx,'alice',at=datetime(2026,10,18,16,0,0))
    await insert_request(ctx,'alice',at=datetime(2026,10,19,16,0,0))
    url='/api/stats/industry-report/groups?dimension=day&start=2026-10-19&end=2026-10-19'
    data=(await ctx.client.get(url,headers=ctx.headers('alice'))).json()
    assert data['items'][0]['name']=='2026-10-19' and data['items'][0]['total']==1
    assert (await ctx.client.get('/api/stats/industry-report?start=2026-10-20&end=2026-10-19',headers=ctx.headers('alice'))).status_code==422


@pytest.mark.asyncio
async def test_menu_validation_and_role_crud(context):
    ctx=context; headers=ctx.headers('cqbank')
    assert (await ctx.client.post('/api/admin/menus',headers=headers,json={'code':'evil','name':'bad','kind':'external','path':'javascript:alert(1)'})).status_code==422
    assert (await ctx.client.post('/api/admin/menus',headers=headers,json={'code':'badpage','name':'bad','path':'/unknown'})).status_code==422
    parent=(await ctx.client.post('/api/admin/menus',headers=headers,json={'code':'directory','name':'目录','kind':'directory'})).json()
    child=(await ctx.client.post('/api/admin/menus',headers=headers,json={'code':'link','name':'外链','kind':'external','path':'https://example.com','parent_id':parent['id']})).json()
    response=await ctx.client.put(f'/api/admin/menus/{parent["id"]}',headers=headers,json={'code':'directory','name':'目录','kind':'directory','parent_id':parent['id']})
    assert response.status_code==422
    assert (await ctx.client.delete(f'/api/admin/menus/{parent["id"]}',headers=headers)).status_code==409
    role=(await ctx.client.post('/api/admin/roles',headers=headers,json={'code':'reader','name':'读者','menu_ids':[child['id']]})).json()
    assert role['menu_ids']==[child['id']]
    assert (await ctx.client.put(f'/api/admin/users/{ctx.ids["bob"]}',headers=headers,json={'role_ids':[role['id']]})).status_code==200
    assert (await ctx.client.get('/api/stats/industry-report',headers=ctx.headers('bob'))).status_code==403
    assert (await ctx.client.delete(f'/api/admin/roles/{role["id"]}',headers=headers)).status_code==409


@pytest.mark.asyncio
async def test_initializer_idempotent_and_missing_admin(context):
    async with context.db() as db:
        user_role=(await db.execute(select(Role).where(Role.code=='user'))).scalar_one()
        user_role.name='自定义普通角色';db.add(user_role);await db.commit()
        await db.execute(delete(UserRole).where(UserRole.user_id == context.ids['bob']))
        menu = (await db.execute(select(Menu).where(Menu.path == '/stats'))).scalar_one()
        menu.path = '/reports'
        db.add(menu)
        await db.commit()
        await seed_rbac(db,administrator='cqbank');await seed_rbac(db,administrator='cqbank')
        roles=list((await db.execute(select(Role))).scalars())
        assert len(roles)==2 and next(r for r in roles if r.code=='user').name=='自定义普通角色'
        assert not (await db.execute(select(UserRole).where(UserRole.user_id == context.ids['bob']))).first()
        assert not (await db.execute(select(Menu).where(Menu.path == '/stats'))).first()
        with pytest.raises(ValueError):await seed_rbac(db,administrator='missing')


@pytest.mark.asyncio
async def test_token_types_and_invalid_refresh_subject(context):
    refresh = create_token(str(context.ids['alice']), 'alice', 'refresh')
    assert (await context.client.get('/api/auth/me', headers={'Authorization': f'Bearer {refresh}'})).status_code == 401
    assert (await context.client.post('/api/auth/refresh', headers=context.headers('alice'))).status_code == 401
    malformed = create_token('not-an-integer', 'alice', 'refresh')
    assert (await context.client.post('/api/auth/refresh', headers={'Authorization': f'Bearer {malformed}'})).status_code == 401


@pytest.mark.asyncio
async def test_explicit_account_bootstrap(context, monkeypatch):
    from app.init import create_user as bootstrap
    monkeypatch.setattr(bootstrap, 'SessionLocal', context.db)
    monkeypatch.setenv('BOOTSTRAP_USER_PASSWORD', 'operator-password-123')
    await bootstrap.create_user('operator')
    async with context.db() as db:
        account = (await db.execute(select(User).where(User.username == 'operator'))).scalar_one()
        assert not (await db.execute(select(UserRole).where(UserRole.user_id == account.id))).first()
        await seed_rbac(db, administrator='operator')
        assert (await db.execute(select(UserRole).join(Role).where(UserRole.user_id == account.id, Role.code == 'admin'))).first()
    with pytest.raises(ValueError):
        await bootstrap.create_user('operator')
