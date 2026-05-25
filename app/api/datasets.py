from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.qa import DatasetExportRequest, DatasetExportResponse, DatasetRowRead, ExportArtifactRead, SeedLoadResponse
from app.services.dataset_service import export_dataset_rows, get_export_artifact, list_dataset_rows, list_export_artifacts
from app.services.seed_service import load_seed_dataset_rows

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/rows", response_model=list[DatasetRowRead])
async def read_dataset_rows(db: AsyncSession = Depends(get_db_session)):
    return await list_dataset_rows(db)


@router.get("/artifacts", response_model=list[ExportArtifactRead])
async def read_export_artifacts(db: AsyncSession = Depends(get_db_session)):
    return await list_export_artifacts(db)


@router.get("/artifacts/{artifact_id}/download")
async def download_export_artifact(artifact_id: str, db: AsyncSession = Depends(get_db_session)):
    artifact = await get_export_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Export artifact not found")
    path = Path(artifact.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Export artifact file not found")
    return FileResponse(path, filename=path.name, media_type=_artifact_media_type(artifact.artifact_type))


@router.post("/export", response_model=DatasetExportResponse)
async def export_dataset(payload: DatasetExportRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await export_dataset_rows(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/seed/load", response_model=SeedLoadResponse)
async def load_seed_dataset(db: AsyncSession = Depends(get_db_session)):
    try:
        return await load_seed_dataset_rows(db)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _artifact_media_type(artifact_type: str) -> str:
    if artifact_type == "csv":
        return "text/csv"
    if artifact_type == "hf_card":
        return "text/markdown"
    if artifact_type in {"jsonl", "mapping", "kaggle_metadata"}:
        return "application/json"
    return "application/octet-stream"
