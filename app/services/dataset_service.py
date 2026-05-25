import json

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import DatasetRow, QaResult, QaSession, ReviewerCorrection, TranscriptTurn


async def list_dataset_rows(db: AsyncSession) -> list[DatasetRow]:
    result = await db.execute(select(DatasetRow).order_by(desc(DatasetRow.created_at)))
    return list(result.scalars().all())


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
