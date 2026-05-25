import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import QaSession, TranscriptTurn, VoiceSession
from app.schemas.qa import QaSessionCreate, TranscriptSubmit
from app.schemas.voice import VoiceConnectRequest, VoiceConnectResponse, VoiceEventRequest, VoiceEventResponse
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


async def submit_voice_event(db: AsyncSession, payload: VoiceEventRequest) -> VoiceEventResponse:
    voice_session = await get_voice_session(db, payload.voice_session_id)
    if not voice_session:
        raise ValueError("Voice session not found")
    if not voice_session.qa_session_id:
        raise ValueError("Voice session is not linked to a QA session")
    qa_session = await get_qa_session(db, voice_session.qa_session_id)
    if not qa_session:
        raise ValueError("QA session not found")

    if payload.event_type in {"partial_transcript", "final_transcript"} and not (payload.transcript or "").strip():
        raise ValueError("Transcript is required for transcript events")

    language = payload.language or qa_session.language
    turn: TranscriptTurn | None = None
    result = None
    if payload.event_type == "final_transcript":
        result = await submit_transcript(
            db,
            qa_session,
            TranscriptSubmit(transcript=payload.transcript or "", source="voice", language=language),
        )
        turn = await _attach_voice_metadata(
            db,
            voice_session.id,
            qa_session_id=qa_session.id,
            confidence=payload.confidence,
            provider_metadata=_event_metadata(payload),
        )
        voice_session.status = "active"
    elif payload.event_type == "partial_transcript":
        turn = _build_partial_turn(qa_session=qa_session, payload=payload, language=language)
        db.add(turn)
        await db.flush()
        voice_session.status = "listening"
    else:
        voice_session.status = _status_for_event(payload.event_type, payload.agent_state)

    _update_voice_metadata(voice_session, payload=payload, turn_id=turn.id if turn else None, qa_result_id=result.id if result else None)
    await db.commit()
    if result:
        await db.refresh(result)
    if turn:
        await db.refresh(turn)
    await db.refresh(voice_session)
    return VoiceEventResponse(
        voice_session_id=voice_session.id,
        qa_session_id=qa_session.id,
        event_type=payload.event_type,
        accepted=True,
        turn_id=turn.id if turn else None,
        qa_result=result,
        recommended_next_action=_recommended_next_action(payload.event_type, result.escalation_required if result else False),
        voice_state=_voice_state(voice_session),
    )


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
) -> TranscriptTurn | None:
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
    return turn


def _build_partial_turn(*, qa_session: QaSession, payload: VoiceEventRequest, language: str) -> TranscriptTurn:
    return TranscriptTurn(
        qa_session_id=qa_session.id,
        voice_session_id=payload.voice_session_id,
        role=payload.role,
        source="voice_partial",
        language=language,
        content=payload.transcript or "",
        confidence=payload.confidence,
        provider_metadata=_event_metadata(payload),
    )


def _event_metadata(payload: VoiceEventRequest) -> dict:
    metadata = dict(payload.provider_metadata)
    metadata["event_type"] = payload.event_type
    if payload.turn_index is not None:
        metadata["turn_index"] = payload.turn_index
    if payload.occurred_at is not None:
        metadata["occurred_at"] = payload.occurred_at.isoformat()
    if payload.agent_state:
        metadata["agent_state"] = payload.agent_state
    if payload.metrics:
        metadata["metrics"] = payload.metrics
    return metadata


def _update_voice_metadata(
    voice_session: VoiceSession,
    *,
    payload: VoiceEventRequest,
    turn_id: str | None,
    qa_result_id: str | None,
) -> None:
    metadata = dict(voice_session.metadata_json)
    metadata["last_event_type"] = payload.event_type
    metadata["last_turn_id"] = turn_id
    metadata["last_qa_result_id"] = qa_result_id
    metadata["event_counts"] = _increment_event_count(metadata.get("event_counts", {}), payload.event_type)
    if payload.transcript:
        metadata["last_transcript_excerpt"] = _excerpt(payload.transcript)
    if payload.agent_state:
        metadata["agent_state"] = payload.agent_state
    if payload.metrics:
        metadata["latest_metrics"] = payload.metrics
    if payload.event_type == "interruption":
        metadata["interruption_count"] = int(metadata.get("interruption_count", 0)) + 1
    voice_session.metadata_json = metadata


def _increment_event_count(counts: dict, event_type: str) -> dict[str, int]:
    normalized = {str(key): int(value) for key, value in counts.items()}
    normalized[event_type] = normalized.get(event_type, 0) + 1
    return normalized


def _status_for_event(event_type: str, agent_state: str | None) -> str:
    if event_type == "interruption":
        return "interrupted"
    if event_type == "agent_state" and agent_state:
        return agent_state
    if event_type == "metrics":
        return "active"
    return "active"


def _recommended_next_action(event_type: str, escalation_required: bool) -> str:
    if event_type == "partial_transcript":
        return "wait_for_final_transcript"
    if event_type == "interruption":
        return "pause_agent_speech_and_resume_listening"
    if event_type == "metrics":
        return "review_latency_if_needed"
    if event_type == "agent_state":
        return "continue_session"
    if escalation_required:
        return "review_escalation"
    return "continue_monitoring"


def _voice_state(voice_session: VoiceSession) -> dict:
    return {
        "status": voice_session.status,
        "metadata": voice_session.metadata_json,
    }


def _excerpt(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


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
