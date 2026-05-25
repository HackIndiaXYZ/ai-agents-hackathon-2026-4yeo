import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
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
async def test_analytics_summary_reflects_backend_activity(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    session_id = _create_reviewed_session(client)

    export_response = client.post("/api/datasets/export", json={"format": "jsonl"})
    assert export_response.status_code == 200

    summary_response = client.get("/api/analytics/summary")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_sessions"] == 1
    assert summary["total_results"] == 1
    assert summary["total_corrections"] == 1
    assert summary["total_dataset_rows"] == 1
    assert summary["total_exports"] == 1
    assert summary["escalation_required_count"] == 1
    assert summary["escalation_rate"] == 1
    assert summary["rows_by_language"] == {"Hinglish": 1}
    assert summary["rows_by_label"] == {"missed_escalation": 1}
    assert summary["rows_by_source"] == {"correction": 1}
    assert summary["latest_adaption_run"]["id"] is None

    session_response = client.get(f"/api/qa/sessions/{session_id}")
    assert session_response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_reports_database_and_export_directory(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))

    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["database"]["ok"] is True
    assert body["export_directory"]["ok"] is True
    assert body["livekit_config"]["ok"] is False
    assert "missing LiveKit" in body["livekit_config"]["detail"]
    assert body["status"] in {"ready", "degraded"}


def _create_reviewed_session(client: TestClient) -> str:
    create_response = client.post(
        "/api/qa/sessions",
        json={"language": "Hinglish", "domain": "fintech_refund", "is_demo": True},
    )
    session_id = create_response.json()["id"]
    client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={"transcript": "Customer: refund stuck hai, please escalate this complaint.", "source": "transcript"},
    )
    correction_response = client.post(
        f"/api/qa/sessions/{session_id}/corrections",
        json={
            "corrected_score": 61,
            "corrected_violation_label": "missed_escalation",
            "corrected_escalation_required": True,
        },
    )
    assert correction_response.status_code == 200
    return session_id
