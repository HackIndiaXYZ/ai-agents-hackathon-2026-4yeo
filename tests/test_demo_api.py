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
async def test_demo_scenarios_are_listed(client):
    response = client.get("/api/demo/scenarios")

    assert response.status_code == 200
    scenarios = response.json()
    assert len(scenarios) == 3
    assert {scenario["language"] for scenario in scenarios} == {"Hinglish", "Hindi", "Indian English"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "expected_label", "expected_escalation"),
    [
        ("fintech-hinglish-refund-escalation", "missed_escalation", True),
        ("ecommerce-hindi-privacy-risk", "privacy_risk", True),
        ("telecom-indian-english-good-handling", "good_handling", False),
    ],
)
async def test_demo_scenario_run_uses_real_qa_workflow(client, scenario_id, expected_label, expected_escalation):
    response = client.post(f"/api/demo/scenarios/{scenario_id}/run")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"]["id"] == scenario_id
    assert body["session"]["is_demo"] is True
    assert body["result"]["violation_label"] == expected_label
    assert body["result"]["escalation_required"] is expected_escalation
    assert body["expected_match"] is True


@pytest.mark.asyncio
async def test_unknown_demo_scenario_returns_not_found(client):
    response = client.post("/api/demo/scenarios/missing/run")

    assert response.status_code == 404
    assert response.json()["detail"] == "Demo scenario not found"
