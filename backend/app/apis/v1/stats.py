from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import select
from app.db.session import get_db
from app.models.models import CallLog
from app.apis.deps import current_user
router = APIRouter(prefix='/stats', tags=['stats'])
@router.get('/calls')
async def calls(db=Depends(get_db), user=Depends(current_user)):
    rows = (await db.execute(select(CallLog.endpoint, func.count(CallLog.id)).group_by(CallLog.endpoint))).all()
    return {'calls': [{'endpoint': r[0], 'count': r[1]} for r in rows]}
