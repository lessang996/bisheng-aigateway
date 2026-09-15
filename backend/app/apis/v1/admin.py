from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.db.session import get_db
from app.models.models import SensitiveRule
from app.schemas import SensitiveRuleCreate, LogLevelRequest
from app.apis.deps import current_user
router = APIRouter(prefix='/admin', tags=['admin'])
@router.post('/sensitive-rules')
async def add_rule(data: SensitiveRuleCreate, db: AsyncSession=Depends(get_db), user=Depends(current_user)):
    rule = SensitiveRule(**data.model_dump()); db.add(rule); await db.commit(); await db.refresh(rule); return {'id': rule.id}
@router.get('/sensitive-rules')
async def list_rules(db: AsyncSession=Depends(get_db), user=Depends(current_user)):
    return (await db.execute(select(SensitiveRule))).scalars().all()
@router.post('/log-level')
async def log_level(data: LogLevelRequest, user=Depends(current_user)):
    import logging
    logging.getLogger().setLevel(data.level.upper()); return {'level': data.level.upper()}
