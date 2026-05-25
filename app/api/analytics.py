from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.analytics import AnalyticsSummary, ReadinessSummary
from app.services.analytics_service import build_analytics_summary, build_readiness_summary

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(db: AsyncSession = Depends(get_db_session)):
    return await build_analytics_summary(db)


@router.get("/health/readiness", response_model=ReadinessSummary)
async def readiness(db: AsyncSession = Depends(get_db_session)):
    return await build_readiness_summary(db)
