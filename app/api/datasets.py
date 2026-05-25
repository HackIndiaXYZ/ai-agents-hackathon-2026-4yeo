from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.qa import DatasetExportRequest, DatasetExportResponse, DatasetRowRead
from app.services.dataset_service import export_dataset_rows, list_dataset_rows

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/rows", response_model=list[DatasetRowRead])
async def read_dataset_rows(db: AsyncSession = Depends(get_db_session)):
    return await list_dataset_rows(db)


@router.post("/export", response_model=DatasetExportResponse)
async def export_dataset(payload: DatasetExportRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await export_dataset_rows(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
