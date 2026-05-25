import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import QaSession, TranscriptTurn, VoiceSession
from app.schemas.qa import QaSessionCreate, TranscriptSubmit
from app.schemas.voice import VoiceConnectRequest, VoiceConnectResponse, VoiceEventRequest
from app.services.session_service import create_qa_session, get_qa_session, submit_transcript


async def connect_voice_session(db: AsyncSession, payload: VoiceConnectRequest) -> VoiceConnectResponse:
    qa_session = await _resolve_qa_session(db, payload)
    settings = get_settings()
    if not settings.livekit.api_key or not settings.livekit.api_secret:
        raise ValueError("LiveKit credentials are required")
    room_name = f"{settings.livekit.room_prefix}-{uuid.uuid4().hex[:12]}"
    voice_session = VoiceSession(
        qa_session_id=qa_session.id,
        room_name=room_name,
        status="created",
        metadata_json={
            "language": qa_session.language,
            "domain": qa_session.domain,
            "participant_identity": payload.participant_identity,
        },
    )
    db.add(voice_session)
    await db.commit()
    await db.refresh(voice_session)
    token = _build_token(
        room_name=room_name,
        participant_identity=payload.participant_identity,
        qa_session_id=qa_session.id,
        voice_session_id=voice_session.id,
    )
    return VoiceConnectResponse(
        token=token,
        livekit_url=settings.livekit.url,
        room_name=room_name,
        voice_session_id=voice_session.id,
        qa_session_id=qa_session.id,
    )


async def submit_voice_event(db: AsyncSession, payload: VoiceEventRequest):
    voice_session = await get_voice_session(db, payload.voice_session_id)
    if not voice_session:
        raise ValueError("Voice session not found")
    if not voice_session.qa_session_id:
        raise ValueError("Voice session is not linked to a QA session")
    qa_session = await get_qa_session(db, voice_session.qa_session_id)
    if not qa_session:
        raise ValueError("QA session not found")

    language = payload.language or qa_session.language
    result = await submit_transcript(
        db,
        qa_session,
        TranscriptSubmit(transcript=payload.transcript, source="voice", language=language),
    )
    await _attach_voice_metadata(
        db,
        voice_session.id,
        qa_session_id=qa_session.id,
        confidence=payload.confidence,
        provider_metadata=payload.provider_metadata,
    )
    voice_session.status = "active"
    await db.commit()
    await db.refresh(result)
    return result


async def get_voice_session(db: AsyncSession, voice_session_id: str) -> VoiceSession | None:
    result = await db.execute(select(VoiceSession).where(VoiceSession.id == voice_session_id))
    return result.scalar_one_or_none()


async def _resolve_qa_session(db: AsyncSession, payload: VoiceConnectRequest) -> QaSession:
    if payload.qa_session_id:
        session = await get_qa_session(db, payload.qa_session_id)
        if not session:
            raise ValueError("QA session not found")
        return session
    return await create_qa_session(
        db,
        QaSessionCreate(
            workspace_id=payload.workspace_id,
            language=payload.language,
            domain=payload.domain,
            scenario_type="voice_session",
        ),
    )


async def _attach_voice_metadata(
    db: AsyncSession,
    voice_session_id: str,
    *,
    qa_session_id: str,
    confidence: float | None,
    provider_metadata: dict,
) -> None:
    result = await db.execute(
        select(TranscriptTurn)
        .where(TranscriptTurn.qa_session_id == qa_session_id)
        .where(TranscriptTurn.voice_session_id.is_(None))
        .where(TranscriptTurn.source == "voice")
        .order_by(TranscriptTurn.created_at.desc())
        .limit(1)
    )
    turn = result.scalar_one_or_none()
    if turn:
        turn.voice_session_id = voice_session_id
        turn.confidence = confidence
        turn.provider_metadata = provider_metadata


def _build_token(*, room_name: str, participant_identity: str, qa_session_id: str, voice_session_id: str) -> str:
    settings = get_settings()
    from livekit.api import AccessToken, VideoGrants

    metadata = {
        "qa_session_id": qa_session_id,
        "voice_session_id": voice_session_id,
    }
    return (
        AccessToken(settings.livekit.api_key, settings.livekit.api_secret)
        .with_identity(participant_identity)
        .with_metadata(json.dumps(metadata))
        .with_grants(VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
        .to_jwt()
    )
