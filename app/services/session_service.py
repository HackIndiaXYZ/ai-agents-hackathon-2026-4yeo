from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import QaResult, QaSession, TranscriptTurn
from app.schemas.qa import QaSessionCreate, TranscriptSubmit
from app.services.qa_service import score_support_transcript


async def create_qa_session(db: AsyncSession, payload: QaSessionCreate) -> QaSession:
    session = QaSession(**payload.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_qa_session(db: AsyncSession, session_id: str) -> QaSession | None:
    result = await db.execute(select(QaSession).where(QaSession.id == session_id))
    return result.scalar_one_or_none()


async def submit_transcript(db: AsyncSession, session: QaSession, payload: TranscriptSubmit) -> QaResult:
    language = payload.language or session.language
    turn = TranscriptTurn(
        qa_session_id=session.id,
        role="conversation",
        source=payload.source,
        language=language,
        content=payload.transcript,
    )
    db.add(turn)

    decision = score_support_transcript(transcript=payload.transcript, language=language, domain=session.domain)
    result = QaResult(qa_session_id=session.id, **decision.__dict__)
    db.add(result)
    await db.flush()

    session.latest_qa_result_id = result.id
    await db.commit()
    await db.refresh(result)
    return result


async def get_latest_result(db: AsyncSession, session: QaSession) -> QaResult | None:
    if session.latest_qa_result_id:
        result = await db.execute(select(QaResult).where(QaResult.id == session.latest_qa_result_id))
        return result.scalar_one_or_none()
    result = await db.execute(
        select(QaResult).where(QaResult.qa_session_id == session.id).order_by(desc(QaResult.created_at)).limit(1)
    )
    return result.scalar_one_or_none()
