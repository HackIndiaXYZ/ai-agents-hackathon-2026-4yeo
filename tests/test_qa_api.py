import pytest
import csv
import json
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
    assert result["model_metadata"]["recommended_tool"] == "escalation_plan"
    assert result["model_metadata"]["recommended_action"] == "create_human_handoff"
    assert "explicit escalation cue" in result["model_metadata"]["score_reason"]

    latest_response = client.get(f"/api/qa/sessions/{session_id}/result")
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == result["id"]


@pytest.mark.asyncio
async def test_unknown_session_returns_not_found(client):
    response = client.get("/api/qa/sessions/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reviewer_correction_creates_dataset_row(client):
    create_response = client.post(
        "/api/qa/sessions",
        json={"language": "Hinglish", "domain": "fintech_refund", "is_demo": True},
    )
    session_id = create_response.json()["id"]
    client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={
            "transcript": "Customer: Mera refund stuck hai and I want this escalated.",
            "source": "transcript",
        },
    )

    correction_response = client.post(
        f"/api/qa/sessions/{session_id}/corrections",
        json={
            "corrected_score": 52,
            "corrected_violation_label": "refund_dispute",
            "corrected_escalation_required": True,
            "corrected_coaching_note": "Escalate the refund dispute and give a clear update timeline.",
            "reviewer_note": "The main issue is refund dispute handling.",
        },
    )

    assert correction_response.status_code == 200
    correction = correction_response.json()
    assert correction["dataset_row_id"]
    assert correction["original_result"]["violation_label"] == "missed_escalation"
    assert correction["corrected_violation_label"] == "refund_dispute"

    corrections_response = client.get(f"/api/qa/sessions/{session_id}/corrections")
    assert corrections_response.status_code == 200
    assert corrections_response.json()[0]["id"] == correction["id"]

    rows_response = client.get("/api/datasets/rows")
    assert rows_response.status_code == 200
    rows = rows_response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == correction["dataset_row_id"]
    assert rows[0]["source_type"] == "correction"
    assert rows[0]["labels"]["violation_label"] == "refund_dispute"
    assert rows[0]["labels"]["escalation_required"] is True


@pytest.mark.asyncio
async def test_reviewer_correction_rejects_unknown_label(client):
    create_response = client.post("/api/qa/sessions", json={"language": "Hinglish", "domain": "fintech_refund"})
    session_id = create_response.json()["id"]
    client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={"transcript": "Customer: please escalate my refund dispute.", "source": "transcript"},
    )

    correction_response = client.post(
        f"/api/qa/sessions/{session_id}/corrections",
        json={"corrected_violation_label": "unsupported_label"},
    )

    assert correction_response.status_code == 400
    assert "Unsupported violation label" in correction_response.json()["detail"]


@pytest.mark.asyncio
async def test_reviewer_correction_requires_existing_result(client):
    create_response = client.post("/api/qa/sessions", json={"language": "Hinglish", "domain": "fintech_refund"})
    session_id = create_response.json()["id"]

    correction_response = client.post(
        f"/api/qa/sessions/{session_id}/corrections",
        json={"corrected_violation_label": "refund_dispute"},
    )

    assert correction_response.status_code == 404
    assert correction_response.json()["detail"] == "QA result not found"


@pytest.mark.asyncio
async def test_dataset_export_writes_jsonl_csv_and_mapping(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    create_response = client.post(
        "/api/qa/sessions",
        json={"language": "Hinglish", "domain": "fintech_refund", "is_demo": True},
    )
    session_id = create_response.json()["id"]
    client.post(
        f"/api/qa/sessions/{session_id}/transcript",
        json={"transcript": "Customer: refund stuck hai, please escalate this complaint.", "source": "transcript"},
    )
    client.post(
        f"/api/qa/sessions/{session_id}/corrections",
        json={
            "corrected_score": 60,
            "corrected_violation_label": "missed_escalation",
            "corrected_escalation_required": True,
            "reviewer_note": "Escalation cue was explicit.",
        },
    )

    export_response = client.post("/api/datasets/export", json={"format": "all"})

    assert export_response.status_code == 200
    export_body = export_response.json()
    assert export_body["row_count"] == 1
    assert export_body["formats"] == ["jsonl", "csv", "mapping", "hf_card", "kaggle_metadata"]
    assert len(export_body["artifacts"]) == 5

    artifacts = {artifact["artifact_type"]: artifact for artifact in export_body["artifacts"]}
    jsonl_path = tmp_path / _filename(artifacts["jsonl"]["path"])
    csv_path = tmp_path / _filename(artifacts["csv"]["path"])
    mapping_path = tmp_path / _filename(artifacts["mapping"]["path"])
    hf_card_path = tmp_path / _filename(artifacts["hf_card"]["path"])
    kaggle_metadata_path = tmp_path / _filename(artifacts["kaggle_metadata"]["path"])

    jsonl_rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert jsonl_rows[0]["labels"]["violation_label"] == "missed_escalation"

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert csv_rows[0]["language"] == "Hinglish"

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert mapping["columns"]["prompt"] == "prompt"
    assert mapping["columns"]["chat"] == "chat_payload"

    hf_card = hf_card_path.read_text(encoding="utf-8")
    assert "Adaption Adaptive Data" in hf_card
    assert "Rows: 1" in hf_card

    kaggle_metadata = json.loads(kaggle_metadata_path.read_text(encoding="utf-8"))
    assert kaggle_metadata["title"] == "Argus Awaaz Multilingual Support QA"
    assert "adaptive-data" in kaggle_metadata["keywords"]

    rows_response = client.get("/api/datasets/rows")
    assert rows_response.json()[0]["export_status"] == "exported"

    artifacts_response = client.get("/api/datasets/artifacts")
    assert artifacts_response.status_code == 200
    artifacts_list = artifacts_response.json()
    assert len(artifacts_list) == 5

    download_response = client.get(f"/api/datasets/artifacts/{artifacts['jsonl']['id']}/download")
    assert download_response.status_code == 200
    assert download_response.text.strip()
    assert "missed_escalation" in download_response.text


@pytest.mark.asyncio
async def test_dataset_export_rejects_empty_dataset(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))

    response = client.post("/api/datasets/export", json={"format": "jsonl"})

    assert response.status_code == 400
    assert response.json()["detail"] == "No dataset rows available for export"


def _filename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
