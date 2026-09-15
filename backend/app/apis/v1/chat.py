from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.deps import current_user
from app.db.session import get_db
from app.schemas import IndustryReportRequest
from app.services.chat_service import industry_report as create_industry_report

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/chat/report")
async def industry_report(
    data: IndustryReportRequest,
    request: Request,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_industry_report(data, request, user, db)
