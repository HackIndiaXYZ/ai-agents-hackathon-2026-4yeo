import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models.domain import TranscriptTurn, VoiceSession


@pytest.fixture()
async def db_context():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db_session

    with TestClient(app) as test_client:
        yield test_client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_voice_connect_creates_session_and_token(db_context, monkeypatch):
    client, _ = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")

    response = client.post(
        "/api/voice/connect",
        json={"language": "Hinglish", "domain": "fintech_refund", "participant_identity": "reviewer-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["livekit_url"]
    assert body["room_name"].startswith("argus-awaaz-")
    assert body["voice_session_id"]
    assert body["qa_session_id"]

    voice_response = client.get(f"/api/voice/sessions/{body['voice_session_id']}")
    assert voice_response.status_code == 200
    assert voice_response.json()["metadata_json"]["participant_identity"] == "reviewer-1"


@pytest.mark.asyncio
async def test_voice_event_routes_transcript_to_qa_workflow(db_context, monkeypatch):
    client, session_factory = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")
    connect_response = client.post(
        "/api/voice/connect",
        json={"language": "Hinglish", "domain": "fintech_refund", "participant_identity": "reviewer-1"},
    )
    voice_session_id = connect_response.json()["voice_session_id"]

    event_response = client.post(
        "/api/voice/events",
        json={
            "voice_session_id": voice_session_id,
            "transcript": "Customer: Mera refund stuck hai, please escalate this complaint.",
            "confidence": 0.91,
            "provider_metadata": {"provider": "test"},
        },
    )

    assert event_response.status_code == 200
    body = event_response.json()
    result = body["qa_result"]
    assert body["event_type"] == "final_transcript"
    assert body["recommended_next_action"] == "review_escalation"
    assert result["violation_label"] == "missed_escalation"
    assert result["escalation_required"] is True

    async with session_factory() as session:
        turns = await session.execute(select(TranscriptTurn))
        turn = turns.scalar_one()
        assert turn.voice_session_id == voice_session_id
        assert turn.confidence == 0.91
        assert turn.provider_metadata["provider"] == "test"
        assert turn.provider_metadata["event_type"] == "final_transcript"
        voice_session = await session.get(VoiceSession, voice_session_id)
        assert voice_session.status == "active"
        assert voice_session.metadata_json["event_counts"]["final_transcript"] == 1


@pytest.mark.asyncio
async def test_partial_voice_event_is_stored_without_qa_scoring(db_context, monkeypatch):
    client, session_factory = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")
    connect_response = client.post(
        "/api/voice/connect",
        json={"language": "Hinglish", "domain": "fintech_refund", "participant_identity": "reviewer-1"},
    )
    voice_session_id = connect_response.json()["voice_session_id"]

    response = client.post(
        "/api/voice/events",
        json={
            "voice_session_id": voice_session_id,
            "event_type": "partial_transcript",
            "transcript": "Customer: refund stuck hai",
            "confidence": 0.72,
            "turn_index": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["qa_result"] is None
    assert body["recommended_next_action"] == "wait_for_final_transcript"
    assert body["voice_state"]["status"] == "listening"

    async with session_factory() as session:
        turns = await session.execute(select(TranscriptTurn))
        turn = turns.scalar_one()
        assert turn.source == "voice_partial"
        assert turn.content == "Customer: refund stuck hai"
        assert turn.provider_metadata["turn_index"] == 1


@pytest.mark.asyncio
async def test_voice_event_tracks_interruption_and_metrics(db_context, monkeypatch):
    client, session_factory = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")
    connect_response = client.post(
        "/api/voice/connect",
        json={"language": "Hinglish", "domain": "fintech_refund", "participant_identity": "reviewer-1"},
    )
    voice_session_id = connect_response.json()["voice_session_id"]

    interruption = client.post(
        "/api/voice/events",
        json={"voice_session_id": voice_session_id, "event_type": "interruption", "provider_metadata": {"reason": "barge_in"}},
    )
    metrics = client.post(
        "/api/voice/events",
        json={
            "voice_session_id": voice_session_id,
            "event_type": "metrics",
            "metrics": {"transcription_delay": 0.18, "total_latency": 0.94},
        },
    )

    assert interruption.status_code == 200
    assert interruption.json()["recommended_next_action"] == "pause_agent_speech_and_resume_listening"
    assert metrics.status_code == 200
    assert metrics.json()["voice_state"]["metadata"]["latest_metrics"]["total_latency"] == 0.94

    async with session_factory() as session:
        voice_session = await session.get(VoiceSession, voice_session_id)
        assert voice_session.metadata_json["interruption_count"] == 1
        assert voice_session.metadata_json["event_counts"]["interruption"] == 1
        assert voice_session.metadata_json["event_counts"]["metrics"] == 1

    timeline_response = client.get(f"/api/voice/sessions/{voice_session_id}/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert timeline["voice_session"]["id"] == voice_session_id
    assert timeline["event_counts"]["interruption"] == 1
    assert timeline["event_counts"]["metrics"] == 1
    assert timeline["latest_metrics"]["total_latency"] == 0.94


@pytest.mark.asyncio
async def test_final_voice_event_requires_transcript(db_context, monkeypatch):
    client, _ = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")
    connect_response = client.post("/api/voice/connect", json={"language": "Hinglish", "domain": "fintech_refund"})
    voice_session_id = connect_response.json()["voice_session_id"]

    response = client.post("/api/voice/events", json={"voice_session_id": voice_session_id, "event_type": "final_transcript"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Transcript is required for transcript events"


@pytest.mark.asyncio
async def test_voice_timeline_includes_turns_and_latest_result(db_context, monkeypatch):
    client, _ = db_context
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-with-at-least-32-bytes")
    connect_response = client.post("/api/voice/connect", json={"language": "Hinglish", "domain": "fintech_refund"})
    voice_session_id = connect_response.json()["voice_session_id"]
    client.post(
        "/api/voice/events",
        json={
            "voice_session_id": voice_session_id,
            "event_type": "partial_transcript",
            "transcript": "Customer refund stuck hai",
        },
    )
    client.post(
        "/api/voice/events",
        json={
            "voice_session_id": voice_session_id,
            "event_type": "final_transcript",
            "transcript": "Customer refund stuck hai, please escalate this complaint.",
        },
    )

    response = client.get(f"/api/voice/sessions/{voice_session_id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert len(body["turns"]) == 2
    assert {turn["source"] for turn in body["turns"]} == {"voice_partial", "voice"}
    assert body["latest_result"]["violation_label"] == "missed_escalation"
    assert body["event_counts"]["partial_transcript"] == 1
    assert body["event_counts"]["final_transcript"] == 1


@pytest.mark.asyncio
async def test_voice_connect_requires_livekit_credentials(db_context, monkeypatch):
    client, _ = db_context
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    response = client.post("/api/voice/connect", json={"language": "Hinglish", "domain": "fintech_refund"})

    assert response.status_code == 400
    assert response.json()["detail"] == "LiveKit credentials are required"
