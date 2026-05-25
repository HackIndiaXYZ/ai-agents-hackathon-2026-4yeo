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
async def test_agent_tool_catalog_exposes_executable_tools(client):
    response = client.get("/api/agent-tools")

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()}
    assert set(tools) == {"policy_lookup", "risk_scan", "escalation_plan", "dataset_readiness", "session_summary"}
    assert tools["risk_scan"]["input_schema"]["required"] == ["transcript", "domain"]
    assert "voice-agent" in tools["policy_lookup"]["tags"]


@pytest.mark.asyncio
async def test_policy_lookup_returns_domain_controls(client):
    response = client.post(
        "/api/agent-tools/run",
        json={"tool_name": "policy_lookup", "input": {"domain": "fintech_refund", "risk_label": "privacy_risk"}},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["domain"] == "fintech_refund"
    assert result["risk_label"] == "privacy_risk"
    assert "OTP" in " ".join(result["prohibited_actions"])
    assert result["review_instruction"].startswith("Prioritize credential safety")


@pytest.mark.asyncio
async def test_risk_scan_and_escalation_plan_work_together(client):
    scan_response = client.post(
        "/api/agent-tools/run",
        json={
            "tool_name": "risk_scan",
            "input": {
                "domain": "fintech_refund",
                "language": "Hinglish",
                "transcript": "Customer: Refund stuck hai. Agent: OTP aur password share kar do.",
            },
        },
    )

    assert scan_response.status_code == 200
    scan = scan_response.json()["result"]
    assert scan["violation_label"] == "privacy_risk"
    assert scan["escalation_required"] is True
    assert scan["recommended_next_tool"] == "escalation_plan"
    assert scan["recommended_action"] == "stop_sensitive_data_collection_and_escalate"
    assert "sensitive credential risk" in scan["score_reason"]

    plan_response = client.post(
        "/api/agent-tools/run",
        json={
            "tool_name": "escalation_plan",
            "input": {
                "domain": "fintech_refund",
                "violation_label": scan["violation_label"],
                "urgency": scan["urgency"],
                "final_score": scan["final_score"],
            },
        },
    )

    assert plan_response.status_code == 200
    plan = plan_response.json()["result"]
    assert plan["priority"] == "P1"
    assert plan["handoff_payload"]["queue"] == "qa_escalation"
    assert "credential" in " ".join(plan["actions"]).lower()


@pytest.mark.asyncio
async def test_dataset_readiness_reflects_seed_rows(client):
    seed_response = client.post("/api/datasets/seed/load")
    assert seed_response.status_code == 200

    response = client.post("/api/agent-tools/run", json={"tool_name": "dataset_readiness", "input": {}})

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["row_count"] == 50
    assert result["export_ready"] is True
    assert result["pending_count"] == 50
    assert result["missing_fields"] == []
    assert result["next_action"] == "export_dataset"


@pytest.mark.asyncio
async def test_session_summary_returns_latest_result_and_next_action(client):
    create_response = client.post(
        "/api/qa/sessions",
        json={"language": "Hinglish", "domain": "fintech_refund", "is_demo": True},
    )
    session_id = create_response.json()["id"]
    transcript_response = client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={
            "transcript": "Customer: refund stuck hai, please escalate to manager.",
            "source": "transcript",
        },
    )
    assert transcript_response.status_code == 200

    response = client.post(
        "/api/agent-tools/run",
        json={"tool_name": "session_summary", "input": {"qa_session_id": session_id}},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["qa_session_id"] == session_id
    assert result["turn_count"] == 1
    assert result["latest_result"]["violation_label"] == "missed_escalation"
    assert result["recommended_next_action"] == "review_escalation"


@pytest.mark.asyncio
async def test_agent_tool_rejects_unknown_tool(client):
    response = client.post("/api/agent-tools/run", json={"tool_name": "unknown", "input": {}})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported agent tool: unknown"
