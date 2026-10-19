"""Request accounting is independent of the response stream and its DB session."""
import asyncio
import logging
import time
from datetime import datetime
from functools import wraps

import anyio
from fastapi import HTTPException
from sqlalchemy import update
from sse_starlette.sse import EventSourceResponse

from app.db.session import SessionLocal
from app.models.models import ChatMessage

logger = logging.getLogger(__name__)


class ReportUsage:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or SessionLocal
        self.started = time.monotonic()
        self.message_id = None
        self.cache_status = 'unknown'
        self.request_id = None
        self.outcome = None
        self.error_code = None
        self.error_summary = None
        self.stage = 'initialization'

    def result(self, outcome, code=None, summary=None):
        self.outcome, self.error_code, self.error_summary = outcome, code, summary

    async def write(self, *, final=False):
        if self.message_id is None:
            return
        values = {'cache_status': self.cache_status}
        if self.request_id is not None:
            values['request_id'] = str(self.request_id)
        if final:
            values.update(execution_status=self.outcome or 'failed', completed_at=datetime.utcnow(),
                          duration_ms=round((time.monotonic()-self.started)*1000, 2),
                          error_code=self.error_code,
                          error_summary=(self.error_summary or '')[:255] or None)
        # Starlette cancels the streaming task on disconnect. Shield only this
        # bounded independent transaction, never the upstream response itself.
        with anyio.move_on_after(5, shield=True):
            try:
                async with self.session_factory() as db:
                    await db.execute(update(ChatMessage).where(
                        ChatMessage.id == self.message_id,
                        ChatMessage.execution_status == 'processing').values(**values))
                    await db.commit()
            except Exception:
                logger.exception('Failed to record report usage message_id=%s', self.message_id)


def track_report(function):
    @wraps(function)
    async def wrapped(data, request, user, db, client):
        usage = ReportUsage()
        request.state.report_usage = usage
        try:
            response = await function(data, request, user, db, client)
        except (asyncio.CancelledError, GeneratorExit):
            usage.result('interrupted', 'CLIENT_DISCONNECTED', '客户端中断请求')
            await usage.write(final=True)
            raise
        except Exception as exc:
            if usage.stage == 'safety':
                code = 'SAFETY_REJECTED' if isinstance(exc, HTTPException) and exc.status_code == 400 else 'SAFETY_ERROR'
                summary = '输入未通过安全审核' if code == 'SAFETY_REJECTED' else '安全审核服务失败'
            else:
                code, summary = 'UPSTREAM_ERROR', '上游调用失败'
            usage.result('failed', code, summary)
            await usage.write(final=True)
            raise
        if not isinstance(response, EventSourceResponse):
            if usage.outcome is None:
                usage.result('failed', 'INCOMPLETE_RESPONSE', '未获得完整结果')
            await usage.write(final=True)
            return response
        original = response.body_iterator

        async def stream():
            try:
                async for event in original:
                    yield event
            except (asyncio.CancelledError, GeneratorExit):
                usage.result('interrupted', 'CLIENT_DISCONNECTED', '客户端中断请求')
                raise
            except Exception:
                usage.result('failed', 'STREAM_ERROR', '流式处理失败')
                raise
            finally:
                if usage.outcome is None:
                    usage.result('failed', 'INCOMPLETE_STREAM', '上游未返回有效完成事件')
                await usage.write(final=True)
                # Closing an interrupted wrapper must also close upstream resources.
                with anyio.move_on_after(5, shield=True):
                    await original.aclose()
        response.body_iterator = stream()
        return response
    return wrapped
