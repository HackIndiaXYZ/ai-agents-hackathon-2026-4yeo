from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import AdaptionRun, DatasetRow, ExportArtifact, QaResult, QaSession, ReviewerCorrection
from app.schemas.analytics import AnalyticsSummary, DependencyStatus, LatestAdaptionRun, ReadinessSummary


async def build_analytics_summary(db: AsyncSession) -> AnalyticsSummary:
    total_sessions = await _count(db, QaSession)
    total_results = await _count(db, QaResult)
    total_corrections = await _count(db, ReviewerCorrection)
    total_dataset_rows = await _count(db, DatasetRow)
    total_exports = await _count(db, ExportArtifact)
    escalation_required_count = await _count_where(db, QaResult, QaResult.escalation_required.is_(True))
    rows = await _dataset_rows(db)
    latest_run = await _latest_adaption_run(db)

    return AnalyticsSummary(
        total_sessions=total_sessions,
        total_results=total_results,
        total_corrections=total_corrections,
        total_dataset_rows=total_dataset_rows,
        total_exports=total_exports,
        escalation_required_count=escalation_required_count,
        escalation_rate=round(escalation_required_count / total_results, 4) if total_results else 0,
        rows_by_language=_count_by(rows, lambda row: row.language),
        rows_by_label=_count_by(rows, lambda row: str(row.labels.get("violation_label", "unknown"))),
        rows_by_source=_count_by(rows, lambda row: row.source_type),
        latest_adaption_run=latest_run,
    )


async def build_readiness_summary(db: AsyncSession) -> ReadinessSummary:
    settings = get_settings()
    database = await _database_status(db)
    export_directory = _export_directory_status(Path(settings.adaption.export_dir))
    livekit_config = DependencyStatus(
        ok=bool(settings.livekit.url and settings.livekit.api_key and settings.livekit.api_secret),
        detail="configured" if settings.livekit.url and settings.livekit.api_key and settings.livekit.api_secret else "missing LiveKit URL or credentials",
    )
    adaption_config = DependencyStatus(
        ok=bool(settings.adaption.api_key and settings.adaption.base_url),
        detail="configured" if settings.adaption.api_key and settings.adaption.base_url else "missing Adaption API key or base URL",
    )
    overall_ok = database.ok and export_directory.ok and livekit_config.ok
    return ReadinessSummary(
        status="ready" if overall_ok else "degraded",
        database=database,
        export_directory=export_directory,
        livekit_config=livekit_config,
        adaption_config=adaption_config,
    )


async def _count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def _count_where(db: AsyncSession, model, condition) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(condition)) or 0


async def _dataset_rows(db: AsyncSession) -> list[DatasetRow]:
    result = await db.execute(select(DatasetRow))
    return list(result.scalars().all())


async def _latest_adaption_run(db: AsyncSession) -> LatestAdaptionRun:
    result = await db.execute(select(AdaptionRun).order_by(AdaptionRun.created_at.desc()).limit(1))
    run = result.scalar_one_or_none()
    if not run:
        return LatestAdaptionRun(id=None, dataset_id=None, run_id=None, status=None, error_message=None)
    return LatestAdaptionRun(
        id=run.id,
        dataset_id=run.dataset_id,
        run_id=run.run_id,
        status=run.status,
        error_message=run.error_message,
    )


def _count_by(rows: list[DatasetRow], key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = key_fn(row)
        counts[key] = counts.get(key, 0) + 1
    return counts


async def _database_status(db: AsyncSession) -> DependencyStatus:
    try:
        await db.execute(text("SELECT 1"))
        return DependencyStatus(ok=True, detail="reachable")
    except Exception as exc:
        return DependencyStatus(ok=False, detail=str(exc))


def _export_directory_status(path: Path) -> DependencyStatus:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".readiness"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return DependencyStatus(ok=True, detail=str(path))
    except OSError as exc:
        return DependencyStatus(ok=False, detail=str(exc))
