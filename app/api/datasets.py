from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.qa import DatasetRowRead
from app.services.dataset_service import list_dataset_rows

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/rows", response_model=list[DatasetRowRead])
async def read_dataset_rows(db: AsyncSession = Depends(get_db_session)):
    return await list_dataset_rows(db)
