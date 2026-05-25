from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adaption.client import AdaptionClient, AdaptionClientError
from app.core.config import get_settings
from app.models.domain import AdaptionRun, DatasetRow, ExportArtifact
from app.schemas.adaption import AdaptionDownloadRequest, AdaptionRunCreate, AdaptionStatusRequest


async def start_adaption_run(db: AsyncSession, payload: AdaptionRunCreate) -> AdaptionRun:
    artifact = await _export_artifact_for_run(db, payload.artifact_id)
    if artifact.artifact_type != "jsonl":
        raise ValueError("Adaption runs require a JSONL export artifact")
    file_path = Path(artifact.path)
    if not file_path.exists():
        raise ValueError(f"Export artifact file is missing: {artifact.path}")

    client = _client_from_settings()
    request_payload = {
        "artifact_id": artifact.id,
        "artifact_path": artifact.path,
        "dataset_name": payload.dataset_name,
        "estimate": payload.estimate,
        "max_rows": payload.max_rows,
    }
    run_record = AdaptionRun(status="starting", request_payload=request_payload, result_summary={})
    db.add(run_record)
    await db.flush()

    try:
        create_response = await client.create_file_dataset(name=payload.dataset_name, file_format="jsonl")
        upload = create_response.get("upload_instructions") or {}
        upload_url = upload.get("url")
        s3_key = upload.get("s3_key")
        if not upload_url or not s3_key:
            raise ValueError("Adaption did not return upload instructions for the dataset")

        await client.upload_file(upload_url=upload_url, path=file_path)
        complete_response = await client.complete_upload(
            name=payload.dataset_name,
            file_format="jsonl",
            file_path=file_path,
            s3_key=s3_key,
        )
        dataset_id = complete_response.get("dataset_id") or create_response.get("dataset_id")
        if not dataset_id:
            raise ValueError("Adaption did not return a dataset id")

        run_response = await client.start_run(dataset_id=dataset_id, estimate=payload.estimate, max_rows=payload.max_rows)
        run_record.dataset_id = dataset_id
        run_record.run_id = run_response.get("run_id")
        run_record.status = "estimate" if payload.estimate else "running"
        run_record.result_summary = {
            "create": _safe_summary(create_response),
            "complete": _safe_summary(complete_response),
            "run": _safe_summary(run_response),
        }
        await _mark_rows_with_adaption_ids(db, dataset_id=dataset_id, run_id=run_record.run_id)
    except (AdaptionClientError, ValueError) as exc:
        run_record.status = "failed"
        run_record.error_message = str(exc)
    await db.commit()
    await db.refresh(run_record)
    return run_record


async def get_adaption_run(db: AsyncSession, run_record_id: str) -> AdaptionRun | None:
    result = await db.execute(select(AdaptionRun).where(AdaptionRun.id == run_record_id))
    return result.scalar_one_or_none()


async def update_adaption_status(db: AsyncSession, payload: AdaptionStatusRequest) -> AdaptionRun:
    run_record = await get_adaption_run(db, payload.run_record_id)
    if not run_record:
        raise ValueError("Adaption run not found")
    if not run_record.dataset_id:
        raise ValueError("Adaption run has no dataset id")

    client = _client_from_settings()
    try:
        status_response = await client.get_status(dataset_id=run_record.dataset_id)
        run_record.status = status_response.get("status", run_record.status)
        run_record.result_summary = {**run_record.result_summary, "status": _safe_summary(status_response)}
        error = status_response.get("error")
        if error:
            run_record.error_message = error.get("message") if isinstance(error, dict) else str(error)
    except AdaptionClientError as exc:
        run_record.status = "failed"
        run_record.error_message = str(exc)
    await db.commit()
    await db.refresh(run_record)
    return run_record


async def download_adaption_result(db: AsyncSession, payload: AdaptionDownloadRequest) -> AdaptionRun:
    run_record = await get_adaption_run(db, payload.run_record_id)
    if not run_record:
        raise ValueError("Adaption run not found")
    if not run_record.dataset_id:
        raise ValueError("Adaption run has no dataset id")

    client = _client_from_settings()
    try:
        content = await client.download(dataset_id=run_record.dataset_id, file_format=payload.file_format)
        output_path = _download_path(run_record.dataset_id, payload.file_format)
        output_path.write_bytes(content)
        run_record.exported_file_path = str(output_path)
        run_record.result_summary = {
            **run_record.result_summary,
            "download": {"file_format": payload.file_format, "bytes": len(content), "path": str(output_path)},
        }
    except AdaptionClientError as exc:
        run_record.status = "failed"
        run_record.error_message = str(exc)
    await db.commit()
    await db.refresh(run_record)
    return run_record


async def _export_artifact_for_run(db: AsyncSession, artifact_id: str | None) -> ExportArtifact:
    if artifact_id:
        result = await db.execute(select(ExportArtifact).where(ExportArtifact.id == artifact_id))
    else:
        result = await db.execute(
            select(ExportArtifact)
            .where(ExportArtifact.artifact_type == "jsonl")
            .order_by(desc(ExportArtifact.created_at))
            .limit(1)
        )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise ValueError("JSONL export artifact not found")
    return artifact


async def _mark_rows_with_adaption_ids(db: AsyncSession, *, dataset_id: str, run_id: str | None) -> None:
    result = await db.execute(select(DatasetRow).where(DatasetRow.export_status == "exported"))
    for row in result.scalars().all():
        row.adaption_dataset_id = dataset_id
        row.adaption_run_id = run_id


def _client_from_settings() -> AdaptionClient:
    settings = get_settings()
    try:
        return AdaptionClient(api_key=settings.adaption.api_key, base_url=settings.adaption.base_url)
    except AdaptionClientError as exc:
        raise ValueError(str(exc)) from exc


def _download_path(dataset_id: str, file_format: str) -> Path:
    output_dir = Path(get_settings().adaption.export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{dataset_id}_adaption_output.{file_format}"


def _safe_summary(payload: dict) -> dict:
    redacted = dict(payload)
    if "upload_instructions" in redacted and isinstance(redacted["upload_instructions"], dict):
        upload = dict(redacted["upload_instructions"])
        if "url" in upload:
            upload["url"] = "[redacted]"
        redacted["upload_instructions"] = upload
    return redacted
