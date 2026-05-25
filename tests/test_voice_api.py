import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models.domain import TranscriptTurn


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
    result = event_response.json()
    assert result["violation_label"] == "missed_escalation"
    assert result["escalation_required"] is True

    async with session_factory() as session:
        turns = await session.execute(select(TranscriptTurn))
        turn = turns.scalar_one()
        assert turn.voice_session_id == voice_session_id
        assert turn.confidence == 0.91
        assert turn.provider_metadata == {"provider": "test"}


@pytest.mark.asyncio
async def test_voice_connect_requires_livekit_credentials(db_context, monkeypatch):
    client, _ = db_context
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

    response = client.post("/api/voice/connect", json={"language": "Hinglish", "domain": "fintech_refund"})

    assert response.status_code == 400
    assert response.json()["detail"] == "LiveKit credentials are required"
