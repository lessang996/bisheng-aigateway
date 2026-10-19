from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select, text

from app.apis.deps import require_permission
from app.db.session import get_db
from app.models.models import CallLog, ChatMessage, User

router = APIRouter(prefix='/api/stats', tags=['stats'])
BEIJING = timezone(timedelta(hours=8))
CacheStatus = Literal['hit', 'miss', 'unavailable', 'error', 'unknown']
ExecutionStatus = Literal['processing', 'success', 'failed', 'interrupted', 'unknown']


def date_boundary(value: date) -> datetime:
    return datetime.combine(value, time.min, BEIJING).astimezone(timezone.utc).replace(tzinfo=None)


async def report_filters(request: Request, start: date | None = None, end: date | None = None,
                         user_id: str | None = Query(None, max_length=255),
                         department: str | None = Query(None, max_length=255),
                         cache_status: CacheStatus | None = None,
                         execution_status: ExecutionStatus | None = None,
                         is_stream: bool | None = None,
                         user=Depends(require_permission('stats:view'))):
    today = datetime.now(BEIJING).date()
    start, end = start or today - timedelta(days=29), end or today
    if start > end or end == date.max:
        raise HTTPException(422, '时间范围无效')
    conditions = [ChatMessage.role == 'user', ChatMessage.business_type == 'industry_report',
                  ChatMessage.created_at >= date_boundary(start),
                  ChatMessage.created_at < date_boundary(end + timedelta(days=1))]
    for column, value in [(ChatMessage.user_id, user_id), (ChatMessage.user_department, department),
                          (ChatMessage.cache_status, cache_status), (ChatMessage.execution_status, execution_status),
                          (ChatMessage.is_stream, is_stream)]:
        if value is not None:
            conditions.append(column == value)
    return conditions


def scoped(request, statement, conditions):
    return request.state.access.constrain(statement.where(*conditions), ChatMessage)


def metrics():
    return [func.count(ChatMessage.id).label('total'),
            *[func.sum(case((ChatMessage.execution_status == s, 1), else_=0)).label(s)
              for s in ('success', 'failed', 'interrupted', 'processing', 'unknown')],
            func.sum(case((ChatMessage.cache_status == 'hit', 1), else_=0)).label('cache_hits'),
            func.sum(case((ChatMessage.cache_status.in_(['hit', 'miss']), 1), else_=0)).label('cache_queries'),
            func.avg(ChatMessage.duration_ms).label('avg_duration_ms')]


def metric_result(row):
    data = dict(row)
    for key in ('total', 'success', 'failed', 'interrupted', 'processing', 'unknown', 'cache_hits', 'cache_queries'):
        data[key] = int(data[key] or 0)
    data['cache_rate'] = round(100 * data['cache_hits'] / data['cache_queries'], 2) if data['cache_queries'] else None
    data['avg_duration_ms'] = round(float(data['avg_duration_ms']), 2) if data['avg_duration_ms'] is not None else None
    return data


@router.get('/industry-report')
@router.get('/industry-report/overview')
async def overview(request: Request, conditions=Depends(report_filters), db=Depends(get_db)):
    row = (await db.execute(scoped(request, select(*metrics()), conditions))).mappings().one()
    return metric_result(row)


@router.get('/industry-report/groups')
async def groups(request: Request, dimension: Literal['user', 'department', 'day', 'month', 'cache'] = 'user',
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 conditions=Depends(report_filters), db=Depends(get_db)):
    if dimension in {'day', 'month'}:
        fmt = '%Y-%m-%d' if dimension == 'day' else '%Y-%m'
        if db.bind.dialect.name == 'sqlite':
            column = func.strftime(fmt, ChatMessage.created_at, '+8 hours')
        else:
            column = func.date_format(func.date_add(ChatMessage.created_at, text('INTERVAL 8 HOUR')), fmt)
    else:
        column = {'user': ChatMessage.user_id, 'department': ChatMessage.user_department,
                  'cache': ChatMessage.cache_status}[dimension]
    statement = scoped(request, select(column.label('name'), *metrics()), conditions).group_by(column)
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    rows = (await db.execute(statement.order_by(column).offset((page-1)*page_size).limit(page_size))).mappings()
    return {'items': [metric_result(row) for row in rows], 'total': total}


DETAIL_FIELDS = ['id', 'session_id', 'user_id', 'local_user_id', 'user_department', 'request_id',
                 'is_stream', 'cache_status', 'execution_status', 'created_at', 'completed_at',
                 'duration_ms', 'error_code', 'error_summary']


def public_message(row):
    data = dict(row)
    for key in ('created_at', 'completed_at'):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].replace(tzinfo=timezone.utc).isoformat()
    return data


@router.get('/industry-report/details')
async def details(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  conditions=Depends(report_filters), db=Depends(get_db)):
    statement = scoped(request, select(*[getattr(ChatMessage, name) for name in DETAIL_FIELDS],
                                      func.substr(ChatMessage.content, 1, 200).label('content')), conditions)
    total = (await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    rows = (await db.execute(statement.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                            .offset((page-1)*page_size).limit(page_size))).mappings()
    return {'total': total, 'items': [public_message(row) for row in rows]}


@router.get('/industry-report/{message_id}')
async def detail(message_id: int, request: Request, db=Depends(get_db), user=Depends(require_permission('stats:view'))):
    statement = scoped(request, select(ChatMessage), [ChatMessage.id == message_id,
                       ChatMessage.role == 'user', ChatMessage.business_type == 'industry_report'])
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, '记录不存在或无权查看')
    answers = (await db.execute(select(ChatMessage.id, ChatMessage.content, ChatMessage.role,
                                      ChatMessage.created_at, ChatMessage.request_id).where(
        ChatMessage.parent_id == row.id, ChatMessage.category == 'answer').order_by(ChatMessage.id))).mappings()
    return {'request': public_message({k: getattr(row, k) for k in [*DETAIL_FIELDS, 'content']}),
            'answers': [public_message(answer) for answer in answers]}


@router.get('/calls')
async def calls(request: Request, db=Depends(get_db), user=Depends(require_permission('stats:view'))):
    access = request.state.access
    statement = select(CallLog.endpoint, func.count(CallLog.id)).group_by(CallLog.endpoint)
    if not access.admin and 'all' not in access.scopes:
        ids = select(User.id).where(User.id == access.user.id)
        if 'department' in access.scopes and access.user.department:
            ids = select(User.id).where((User.id == access.user.id) | (User.department == access.user.department))
        statement = statement.where(CallLog.user_id.in_(ids))
    return {'calls': [{'endpoint': r[0], 'count': r[1]} for r in (await db.execute(statement)).all()]}
