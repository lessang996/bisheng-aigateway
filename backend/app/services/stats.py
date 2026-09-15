from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import CallLog
async def record_call(db: AsyncSession, request, status: int, duration: float, user_id=None):
    db.add(CallLog(user_id=user_id, endpoint=request.url.path, method=request.method, status_code=status, duration=duration, ip_address=request.client.host if request.client else '')); await db.commit()
