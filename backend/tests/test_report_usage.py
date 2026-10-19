import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlmodel import select

from test_rbac_stats import context
from app.models.models import ChatMessage
from app.schemas.industry_report import IndustryReportRequest
from app.services import chat_service
from app.services.report_usage import ReportUsage


TEXT = {'event': 'TEXT_DELTA', 'data': json.dumps({'eventType':'TEXT_DELTA','data':{'type':'text','text':'hello'}})}
DONE = {'event':'MESSAGE_COMPLETED','data':json.dumps({'eventType':'MESSAGE_COMPLETED','terminal':True,'data':{'finishReason':'STOP'}})}


class Cache:
    def __init__(self, value=None, error=False):
        self.value, self.error = value, error
    async def get_json(self, key):
        if self.error: raise RuntimeError('redis unavailable')
        return self.value if key.startswith('industry_report:') else None
    async def set_json(self, *args, **kwargs):
        pass


class Client:
    def __init__(self, events=None, status='COMPLETED', empty=False, error=False):
        self.events = [TEXT,DONE] if events is None else events
        self.status, self.empty, self.error = status, empty, error
    async def post(self,*args,**kwargs):
        if self.error: raise RuntimeError('upstream unavailable')
        return SimpleNamespace(status_code=200,json=lambda:{'success':True,'data':{'requestId':'upstream-id','sessionId':'upstream-session'}})
    async def get(self,*args,**kwargs):
        return SimpleNamespace(status_code=200,json=lambda:{'success':True,'data':{'requestId':'upstream-id','status':self.status,'assistantReply':'' if self.empty else 'hello'}})
    @asynccontextmanager
    async def stream(self,*args,**kwargs):
        async def lines():
            for event in self.events:
                yield 'event: '+event['event']
                yield 'data: '+event['data']
                yield ''
        yield SimpleNamespace(status_code=200,headers={},aiter_lines=lines)


async def invoke(ctx, monkeypatch, *, stream=True, cache=None, client=None, reject=False, internal_stream=False, consume=True):
    settings=SimpleNamespace(agent_id=1,redis_cache_ttl=86400,safety_filter_enabled=reject,
                             external_api_url='https://upstream.invalid',nonstream_use=internal_stream,max_polls=0,poll_interval=0)
    monkeypatch.setattr(chat_service,'get_settings',lambda:settings)
    async def principal(*args):return 1
    monkeypatch.setattr(chat_service,'get_or_create_principal',principal)
    class Guard:
        def __init__(self,*args):pass
        async def analyze_input(self,*args):return {'action':1,'isSafe':0}
    monkeypatch.setattr(chat_service,'SafetyGuard',Guard)
    request=Request({'type':'http','method':'POST','path':'/api/chat/report','headers':[],
                     'app':SimpleNamespace(state=SimpleNamespace(redis=cache))})
    async with ctx.db() as db:
        response=await chat_service.industry_report(IndustryReportRequest(userInput='question',stream=stream),request,
                         {'userNo':'alice','org':'A','local_user_id':ctx.ids['alice']},db,client or Client())
        if stream and consume:
            events=[event async for event in response.body_iterator]
            return events
        return response


async def question(ctx):
    async with ctx.db() as db:
        return (await db.execute(select(ChatMessage).where(ChatMessage.role=='user').order_by(ChatMessage.id.desc()))).scalars().first()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [True,False])
@pytest.mark.parametrize('mode', ['hit','miss','unavailable','error'])
async def test_report_cache_modes(context,monkeypatch,stream,mode):
    value=[TEXT,DONE] if stream else {'data':{'assistantReply':'cached'}}
    cache=None if mode=='unavailable' else Cache(value if mode=='hit' else None,error=mode=='error')
    result=await invoke(context,monkeypatch,stream=stream,cache=cache)
    row=await question(context)
    assert row.cache_status==mode and row.execution_status=='success'
    assert row.local_user_id==context.ids['alice'] and row.duration_ms>=0 and row.completed_at is not None
    if stream and mode=='hit':assert result==value


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [('FAILED','failed'),('CANCELLED','interrupted'),('RUNNING','failed')])
async def test_nonstream_failure(context,monkeypatch,status,expected):
    await invoke(context,monkeypatch,stream=False,client=Client(status=status))
    row=await question(context)
    assert row.execution_status==expected and row.error_code


@pytest.mark.asyncio
@pytest.mark.parametrize('internal_stream',[False,True])
async def test_empty_success(context,monkeypatch,internal_stream):
    await invoke(context,monkeypatch,stream=False,client=Client(events=[DONE],empty=True),internal_stream=internal_stream)
    assert (await question(context)).execution_status=='success'


@pytest.mark.asyncio
async def test_eof_and_duplicate_terminal(context,monkeypatch):
    await invoke(context,monkeypatch,client=Client(events=[TEXT]))
    assert (await question(context)).execution_status=='failed'
    await invoke(context,monkeypatch,client=Client(events=[TEXT,DONE,DONE]))
    row=await question(context)
    assert row.execution_status=='success'
    async with context.db() as db:
        answers=list((await db.execute(select(ChatMessage).where(ChatMessage.parent_id==row.id))).scalars())
        assert len(answers)==1


@pytest.mark.asyncio
async def test_rejected_and_upstream_exception(context,monkeypatch):
    with pytest.raises(HTTPException):await invoke(context,monkeypatch,reject=True)
    row=await question(context)
    assert row.execution_status=='failed' and row.error_code=='SAFETY_REJECTED'
    with pytest.raises(HTTPException):await invoke(context,monkeypatch,client=Client(error=True))
    assert (await question(context)).execution_status=='failed'


@pytest.mark.asyncio
async def test_cancelled_cache_and_idempotent_finalize(context,monkeypatch):
    response=await invoke(context,monkeypatch,cache=Cache([TEXT,DONE]),consume=False)
    await anext(response.body_iterator)
    with anyio.CancelScope() as scope:
        scope.cancel()
        await response.body_iterator.aclose()
    row=await question(context)
    assert row.execution_status=='interrupted' and row.cache_status=='hit'
    tracker=ReportUsage(context.db)
    tracker.message_id=row.id;tracker.result('success');await tracker.write(final=True)
    assert (await question(context)).execution_status=='interrupted'
