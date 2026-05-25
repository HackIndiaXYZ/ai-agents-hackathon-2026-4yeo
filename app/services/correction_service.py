from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import QaResult, QaSession, ReviewerCorrection
from app.schemas.qa import ReviewerCorrectionCreate
from app.services.dataset_service import build_dataset_row_from_correction, qa_result_snapshot


async def create_reviewer_correction(
    db: AsyncSession,
    session: QaSession,
    qa_result: QaResult,
    payload: ReviewerCorrectionCreate,
) -> ReviewerCorrection:
    _validate_correction_label(payload.corrected_violation_label)
    correction = ReviewerCorrection(
        qa_session_id=session.id,
        qa_result_id=qa_result.id,
        original_result=qa_result_snapshot(qa_result),
        corrected_transcript=payload.corrected_transcript,
        corrected_score=payload.corrected_score,
        corrected_violation_label=payload.corrected_violation_label,
        corrected_escalation_required=payload.corrected_escalation_required,
        corrected_coaching_note=payload.corrected_coaching_note,
        reviewer_note=payload.reviewer_note,
        accepted=payload.accepted,
    )
    db.add(correction)
    await db.flush()

    dataset_row = await build_dataset_row_from_correction(db, session=session, qa_result=qa_result, correction=correction)
    db.add(dataset_row)
    await db.flush()

    correction.dataset_row_id = dataset_row.id
    await db.commit()
    await db.refresh(correction)
    return correction


async def list_session_corrections(db: AsyncSession, session_id: str) -> list[ReviewerCorrection]:
    result = await db.execute(
        select(ReviewerCorrection)
        .where(ReviewerCorrection.qa_session_id == session_id)
        .order_by(desc(ReviewerCorrection.created_at))
    )
    return list(result.scalars().all())


def _validate_correction_label(label: str | None) -> None:
    if label is None:
        return
    supported_labels = set(get_settings().workflow.violation_labels)
    if label not in supported_labels:
        raise ValueError(f"Unsupported violation label: {label}")
