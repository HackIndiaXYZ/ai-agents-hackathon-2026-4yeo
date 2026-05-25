from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.adaption import AdaptionDownloadRequest, AdaptionRunCreate, AdaptionRunRead, AdaptionStatusRequest
from app.services.adaption_service import download_adaption_result, get_adaption_run, start_adaption_run, update_adaption_status

router = APIRouter(prefix="/adaption", tags=["adaption"])


@router.post("/runs", response_model=AdaptionRunRead)
async def create_run(payload: AdaptionRunCreate, db: AsyncSession = Depends(get_db_session)):
    try:
        return await start_adaption_run(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=AdaptionRunRead)
async def read_run(run_id: str, db: AsyncSession = Depends(get_db_session)):
    run = await get_adaption_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Adaption run not found")
    return run


@router.post("/status", response_model=AdaptionRunRead)
async def refresh_status(payload: AdaptionStatusRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await update_adaption_status(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/download", response_model=AdaptionRunRead)
async def download_result(payload: AdaptionDownloadRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await download_adaption_result(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
