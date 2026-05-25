import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import AdaptionRun, DatasetRow, ExportArtifact, QaResult, QaSession, ReviewerCorrection, TranscriptTurn, VoiceSession
from app.schemas.demo import DemoResetRequest, DemoResetResponse, DemoScenario, DemoScenarioRun
from app.schemas.qa import QaSessionCreate, TranscriptSubmit
from app.services.session_service import create_qa_session, submit_transcript


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_scenarios.json"


@lru_cache
def list_demo_scenarios() -> list[DemoScenario]:
    payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return [DemoScenario.model_validate(item) for item in payload]


async def run_demo_scenario(db: AsyncSession, scenario_id: str) -> DemoScenarioRun:
    scenario = _scenario_by_id(scenario_id)
    session = await create_qa_session(
        db,
        QaSessionCreate(
            language=scenario.language,
            domain=scenario.domain,
            scenario_type=scenario.scenario_type,
            is_demo=True,
        ),
    )
    result = await submit_transcript(
        db,
        session,
        TranscriptSubmit(transcript=scenario.transcript, source="demo", language=scenario.language),
    )
    expected_match = (
        result.violation_label == scenario.expected_violation_label
        and result.escalation_required == scenario.expected_escalation_required
    )
    return DemoScenarioRun(scenario=scenario, session=session, result=result, expected_match=expected_match)


async def reset_demo_state(db: AsyncSession, payload: DemoResetRequest) -> DemoResetResponse:
    if not payload.confirm:
        raise ValueError("Demo reset requires confirm=true")

    session_ids = await _demo_session_ids(db)
    voice_session_ids = await _voice_session_ids(db, include_all=payload.include_voice_sessions, session_ids=session_ids)
    if payload.include_voice_sessions:
        linked_session_ids = await _voice_linked_session_ids(db, voice_session_ids)
        session_ids = sorted({*session_ids, *linked_session_ids})

    counts: dict[str, int] = {}
    counts["transcript_turns"] = await _delete_transcript_turns(db, session_ids=session_ids, voice_session_ids=voice_session_ids)
    counts["reviewer_corrections"] = await _delete_by_session_ids(db, ReviewerCorrection, ReviewerCorrection.qa_session_id, session_ids)
    counts["qa_results"] = await _delete_by_session_ids(db, QaResult, QaResult.qa_session_id, session_ids)
    counts["dataset_rows"] = await _delete_dataset_rows(db, session_ids=session_ids, include_seed_data=payload.include_seed_data)
    counts["qa_sessions"] = await _delete_by_ids(db, QaSession, session_ids)
    counts["voice_sessions"] = await _delete_by_ids(db, VoiceSession, voice_session_ids)
    counts["export_artifacts"] = await _delete_export_artifacts(db) if payload.include_exports else 0
    counts["adaption_runs"] = await _delete_all(db, AdaptionRun) if payload.include_adaption_runs else 0
    await db.commit()
    return DemoResetResponse(deleted_counts=counts)


def _scenario_by_id(scenario_id: str) -> DemoScenario:
    for scenario in list_demo_scenarios():
        if scenario.id == scenario_id:
            return scenario
    raise ValueError("Demo scenario not found")


async def _demo_session_ids(db: AsyncSession) -> list[str]:
    result = await db.execute(select(QaSession.id).where(QaSession.is_demo.is_(True)))
    return list(result.scalars().all())


async def _voice_session_ids(db: AsyncSession, *, include_all: bool, session_ids: list[str]) -> list[str]:
    if include_all:
        result = await db.execute(select(VoiceSession.id))
    elif session_ids:
        result = await db.execute(select(VoiceSession.id).where(VoiceSession.qa_session_id.in_(session_ids)))
    else:
        return []
    return list(result.scalars().all())


async def _voice_linked_session_ids(db: AsyncSession, voice_session_ids: list[str]) -> list[str]:
    if not voice_session_ids:
        return []
    result = await db.execute(
        select(VoiceSession.qa_session_id).where(VoiceSession.id.in_(voice_session_ids)).where(VoiceSession.qa_session_id.is_not(None))
    )
    return [session_id for session_id in result.scalars().all() if session_id]


async def _delete_transcript_turns(db: AsyncSession, *, session_ids: list[str], voice_session_ids: list[str]) -> int:
    conditions = []
    if session_ids:
        conditions.append(TranscriptTurn.qa_session_id.in_(session_ids))
    if voice_session_ids:
        conditions.append(TranscriptTurn.voice_session_id.in_(voice_session_ids))
    if not conditions:
        return 0
    result = await db.execute(delete(TranscriptTurn).where(or_(*conditions)))
    return int(result.rowcount or 0)


async def _delete_dataset_rows(db: AsyncSession, *, session_ids: list[str], include_seed_data: bool) -> int:
    conditions = []
    if session_ids:
        conditions.append(DatasetRow.qa_session_id.in_(session_ids))
    if include_seed_data:
        conditions.append(DatasetRow.source_type == "seed")
    if not conditions:
        return 0
    result = await db.execute(delete(DatasetRow).where(conditions[0]))
    deleted = int(result.rowcount or 0)
    for condition in conditions[1:]:
        result = await db.execute(delete(DatasetRow).where(condition))
        deleted += int(result.rowcount or 0)
    return deleted


async def _delete_by_session_ids(db: AsyncSession, model, column, session_ids: list[str]) -> int:
    if not session_ids:
        return 0
    result = await db.execute(delete(model).where(column.in_(session_ids)))
    return int(result.rowcount or 0)


async def _delete_by_ids(db: AsyncSession, model, ids: list[str]) -> int:
    if not ids:
        return 0
    result = await db.execute(delete(model).where(model.id.in_(ids)))
    return int(result.rowcount or 0)


async def _delete_all(db: AsyncSession, model) -> int:
    result = await db.execute(delete(model))
    return int(result.rowcount or 0)


async def _delete_export_artifacts(db: AsyncSession) -> int:
    result = await db.execute(select(ExportArtifact))
    artifacts = list(result.scalars().all())
    for artifact in artifacts:
        Path(artifact.path).unlink(missing_ok=True)
    delete_result = await db.execute(delete(ExportArtifact))
    return int(delete_result.rowcount or 0)
