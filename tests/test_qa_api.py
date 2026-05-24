import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture()
async def client():
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
        yield test_client

    await engine.dispose()


@pytest.mark.asyncio
async def test_transcript_flow_creates_structured_qa_result(client):
    create_response = client.post(
        "/api/qa/sessions",
        json={"language": "Hinglish", "domain": "fintech_refund", "is_demo": True},
    )
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    result_response = client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={
            "transcript": "Customer: Mera refund abhi tak nahi aaya. I am frustrated, please escalate to manager.",
            "source": "transcript",
        },
    )

    assert result_response.status_code == 200
    result = result_response.json()
    assert result["violation_label"] == "missed_escalation"
    assert result["escalation_required"] is True
    assert result["urgency"] == "high"
    assert result["final_score"] < 80

    latest_response = client.get(f"/api/qa/sessions/{session_id}/result")
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == result["id"]


@pytest.mark.asyncio
async def test_unknown_session_returns_not_found(client):
    response = client.get("/api/qa/sessions/missing")

    assert response.status_code == 404
