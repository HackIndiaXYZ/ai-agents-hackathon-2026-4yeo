from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.qa import QaResultRead
from app.schemas.voice import VoiceConnectRequest, VoiceConnectResponse, VoiceEventRequest, VoiceSessionRead
from app.services.voice_service import connect_voice_session, get_voice_session, submit_voice_event

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/connect", response_model=VoiceConnectResponse)
async def connect_voice(payload: VoiceConnectRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await connect_voice_session(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/events", response_model=QaResultRead)
async def create_voice_event(payload: VoiceEventRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await submit_voice_event(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{voice_session_id}", response_model=VoiceSessionRead)
async def read_voice_session(voice_session_id: str, db: AsyncSession = Depends(get_db_session)):
    session = await get_voice_session(db, voice_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Voice session not found")
    return session
