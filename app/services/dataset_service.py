import json
import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import DatasetRow, ExportArtifact, QaResult, QaSession, ReviewerCorrection, TranscriptTurn
from app.schemas.qa import DatasetExportRequest, DatasetExportResponse


async def list_dataset_rows(db: AsyncSession) -> list[DatasetRow]:
    result = await db.execute(select(DatasetRow).order_by(desc(DatasetRow.created_at)))
    return list(result.scalars().all())


async def export_dataset_rows(db: AsyncSession, payload: DatasetExportRequest) -> DatasetExportResponse:
    rows = await _dataset_rows_for_export(db, version=payload.version)
    if not rows:
        raise ValueError("No dataset rows available for export")

    _validate_rows_for_export(rows)
    export_dir = _export_directory()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    formats = _requested_formats(payload.format)
    artifacts: list[ExportArtifact] = []

    if "jsonl" in formats:
        artifacts.append(await _write_jsonl_artifact(db, export_dir, stamp, rows))
    if "csv" in formats:
        artifacts.append(await _write_csv_artifact(db, export_dir, stamp, rows))
    if "mapping" in formats:
        artifacts.append(await _write_mapping_artifact(db, export_dir, stamp, rows))

    for row in rows:
        row.export_status = "exported"

    await db.commit()
    for artifact in artifacts:
        await db.refresh(artifact)

    return DatasetExportResponse(artifacts=artifacts, row_count=len(rows), formats=formats)


async def latest_transcript_for_session(db: AsyncSession, session_id: str) -> TranscriptTurn | None:
    result = await db.execute(
        select(TranscriptTurn).where(TranscriptTurn.qa_session_id == session_id).order_by(desc(TranscriptTurn.created_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def build_dataset_row_from_correction(
    db: AsyncSession,
    *,
    session: QaSession,
    qa_result: QaResult,
    correction: ReviewerCorrection,
) -> DatasetRow:
    transcript_turn = await latest_transcript_for_session(db, session.id)
    transcript = correction.corrected_transcript or (transcript_turn.content if transcript_turn else "")
    violation_label = correction.corrected_violation_label or qa_result.violation_label
    escalation_required = (
        correction.corrected_escalation_required
        if correction.corrected_escalation_required is not None
        else qa_result.escalation_required
    )
    score = correction.corrected_score if correction.corrected_score is not None else qa_result.final_score
    coaching_note = correction.corrected_coaching_note or qa_result.coaching_note

    completion = {
        "score": score,
        "violation_label": violation_label,
        "escalation_required": escalation_required,
        "coaching_note": coaching_note,
        "ideal_response": qa_result.ideal_response,
    }
    labels = {
        "violation_label": violation_label,
        "escalation_required": escalation_required,
        "sentiment": qa_result.sentiment,
        "urgency": qa_result.urgency,
        "source": "reviewer_correction",
    }

    return DatasetRow(
        source_type="correction",
        qa_session_id=session.id,
        correction_id=correction.id,
        language=session.language,
        domain=session.domain,
        prompt="Evaluate the support-call transcript for QA score, policy risk, escalation need, and coaching feedback.",
        completion=json.dumps(completion, ensure_ascii=False, sort_keys=True),
        context=_dataset_context(session=session, qa_result=qa_result),
        chat_payload={"messages": [{"role": "conversation", "content": transcript}]},
        labels=labels,
        version="v0",
        export_status="pending",
    )


def qa_result_snapshot(result: QaResult) -> dict:
    return {
        "id": result.id,
        "final_score": result.final_score,
        "empathy_score": result.empathy_score,
        "compliance_score": result.compliance_score,
        "escalation_score": result.escalation_score,
        "resolution_score": result.resolution_score,
        "language_clarity_score": result.language_clarity_score,
        "sentiment": result.sentiment,
        "urgency": result.urgency,
        "violation_label": result.violation_label,
        "escalation_required": result.escalation_required,
        "policy_flags": result.policy_flags,
        "evidence_spans": result.evidence_spans,
        "coaching_note": result.coaching_note,
        "ideal_response": result.ideal_response,
        "model_metadata": result.model_metadata,
    }


def _dataset_context(*, session: QaSession, qa_result: QaResult) -> str:
    return json.dumps(
        {
            "language": session.language,
            "dialect_or_style": session.dialect_or_style,
            "domain": session.domain,
            "scenario_type": session.scenario_type,
            "policy_flags": qa_result.policy_flags,
            "evidence_spans": qa_result.evidence_spans,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


async def _dataset_rows_for_export(db: AsyncSession, *, version: str | None) -> list[DatasetRow]:
    query = select(DatasetRow).order_by(DatasetRow.created_at)
    if version:
        query = query.where(DatasetRow.version == version)
    result = await db.execute(query)
    return list(result.scalars().all())


def _validate_rows_for_export(rows: list[DatasetRow]) -> None:
    missing: list[str] = []
    for row in rows:
        if not row.prompt.strip():
            missing.append(f"{row.id}:prompt")
        if not row.completion.strip():
            missing.append(f"{row.id}:completion")
        if not row.context.strip():
            missing.append(f"{row.id}:context")
        if not row.chat_payload:
            missing.append(f"{row.id}:chat_payload")
        if not row.labels:
            missing.append(f"{row.id}:labels")
    if missing:
        raise ValueError(f"Dataset rows are not export ready: {', '.join(missing)}")


def _export_directory() -> Path:
    path = Path(get_settings().adaption.export_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _requested_formats(format_name: str) -> list[str]:
    normalized = format_name.lower().strip()
    if normalized == "all":
        return ["jsonl", "csv", "mapping"]
    if normalized not in {"jsonl", "csv", "mapping"}:
        raise ValueError(f"Unsupported export format: {format_name}")
    return [normalized]


async def _write_jsonl_artifact(db: AsyncSession, export_dir: Path, stamp: str, rows: list[DatasetRow]) -> ExportArtifact:
    path = export_dir / f"argus_awaaz_dataset_{stamp}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(_row_payload(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return await _record_artifact(db, artifact_type="jsonl", path=path, row_count=len(rows), metadata={"format": "jsonl"})


async def _write_csv_artifact(db: AsyncSession, export_dir: Path, stamp: str, rows: list[DatasetRow]) -> ExportArtifact:
    path = export_dir / f"argus_awaaz_dataset_{stamp}.csv"
    fields = [
        "id",
        "source_type",
        "language",
        "domain",
        "prompt",
        "completion",
        "context",
        "chat_payload",
        "labels",
        "version",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            payload = _row_payload(row)
            payload["chat_payload"] = json.dumps(payload["chat_payload"], ensure_ascii=False, sort_keys=True)
            payload["labels"] = json.dumps(payload["labels"], ensure_ascii=False, sort_keys=True)
            writer.writerow({field: payload[field] for field in fields})
    return await _record_artifact(db, artifact_type="csv", path=path, row_count=len(rows), metadata={"format": "csv"})


async def _write_mapping_artifact(db: AsyncSession, export_dir: Path, stamp: str, rows: list[DatasetRow]) -> ExportArtifact:
    path = export_dir / f"argus_awaaz_adaption_mapping_{stamp}.json"
    mapping = {
        "dataset": "argus-awaaz-multilingual-support-qa",
        "row_count": len(rows),
        "columns": {
            "prompt": "prompt",
            "completion": "completion",
            "context": "context",
            "chat": "chat_payload",
        },
        "metadata_columns": ["id", "source_type", "language", "domain", "labels", "version"],
        "credit": "Dataset prepared for the Adaption Adaptive Data workflow.",
    }
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return await _record_artifact(db, artifact_type="mapping", path=path, row_count=len(rows), metadata=mapping)


async def _record_artifact(
    db: AsyncSession,
    *,
    artifact_type: str,
    path: Path,
    row_count: int,
    metadata: dict,
) -> ExportArtifact:
    artifact = ExportArtifact(
        artifact_type=artifact_type,
        path=str(path),
        row_count=row_count,
        metadata_json=metadata,
    )
    db.add(artifact)
    await db.flush()
    return artifact


def _row_payload(row: DatasetRow) -> dict:
    return {
        "id": row.id,
        "source_type": row.source_type,
        "language": row.language,
        "domain": row.domain,
        "prompt": row.prompt,
        "completion": row.completion,
        "context": row.context,
        "chat_payload": row.chat_payload,
        "labels": row.labels,
        "version": row.version,
    }
