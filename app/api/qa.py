from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.qa import QaResultRead, QaSessionCreate, QaSessionRead, ReviewerCorrectionCreate, ReviewerCorrectionRead, TranscriptSubmit
from app.services.correction_service import create_reviewer_correction, list_session_corrections
from app.services.session_service import create_qa_session, get_latest_result, get_qa_session, submit_transcript

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/sessions", response_model=QaSessionRead)
async def create_session(payload: QaSessionCreate, db: AsyncSession = Depends(get_db_session)):
    return await create_qa_session(db, payload)


@router.get("/sessions/{session_id}", response_model=QaSessionRead)
async def read_session(session_id: str, db: AsyncSession = Depends(get_db_session)):
    session = await get_qa_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="QA session not found")
    return session


@router.post("/sessions/{session_id}/transcript", response_model=QaResultRead)
async def submit_session_transcript(session_id: str, payload: TranscriptSubmit, db: AsyncSession = Depends(get_db_session)):
    session = await get_qa_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="QA session not found")
    return await submit_transcript(db, session, payload)


@router.get("/sessions/{session_id}/result", response_model=QaResultRead)
async def read_latest_result(session_id: str, db: AsyncSession = Depends(get_db_session)):
    session = await get_qa_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="QA session not found")
    result = await get_latest_result(db, session)
    if not result:
        raise HTTPException(status_code=404, detail="QA result not found")
    return result


@router.post("/sessions/{session_id}/corrections", response_model=ReviewerCorrectionRead)
async def create_correction(session_id: str, payload: ReviewerCorrectionCreate, db: AsyncSession = Depends(get_db_session)):
    session = await get_qa_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="QA session not found")
    result = await get_latest_result(db, session)
    if not result:
        raise HTTPException(status_code=404, detail="QA result not found")
    try:
        return await create_reviewer_correction(db, session, result, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/corrections", response_model=list[ReviewerCorrectionRead])
async def read_session_corrections(session_id: str, db: AsyncSession = Depends(get_db_session)):
    session = await get_qa_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="QA session not found")
    return await list_session_corrections(db, session_id)
