import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adaption.client import AdaptionClient, AdaptionClientError
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.services import adaption_service


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


def test_adaption_client_requires_credentials():
    with pytest.raises(AdaptionClientError, match="API key"):
        AdaptionClient(api_key="", base_url="https://api.adaptionlabs.ai/api/v1")


@pytest.mark.asyncio
async def test_adaption_run_uploads_export_and_tracks_status(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    fake_client = FakeAdaptionClient()
    monkeypatch.setattr(adaption_service, "_client_from_settings", lambda: fake_client)

    artifact_id = _create_export_artifact(client)

    run_response = client.post(
        "/api/adaption/runs",
        json={"artifact_id": artifact_id, "dataset_name": "argus-awaaz-test", "max_rows": 10},
    )

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["dataset_id"] == "dataset-test"
    assert run["run_id"] == "run-test"
    assert run["status"] == "running"
    assert fake_client.uploaded_path.exists()

    status_response = client.post("/api/adaption/status", json={"run_record_id": run["id"]})
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"

    download_response = client.post("/api/adaption/download", json={"run_record_id": run["id"], "file_format": "jsonl"})
    assert download_response.status_code == 200
    downloaded_path = tmp_path / "dataset-test_adaption_output.jsonl"
    assert downloaded_path.read_text(encoding="utf-8") == '{"processed": true}\n'


@pytest.mark.asyncio
async def test_adaption_run_requires_jsonl_artifact(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    monkeypatch.setattr(adaption_service, "_client_from_settings", lambda: FakeAdaptionClient())
    _create_export_artifact(client)
    rows_response = client.post("/api/datasets/export", json={"format": "csv"})
    csv_artifact = rows_response.json()["artifacts"][0]

    run_response = client.post(
        "/api/adaption/runs",
        json={"artifact_id": csv_artifact["id"], "dataset_name": "argus-awaaz-test"},
    )

    assert run_response.status_code == 400
    assert run_response.json()["detail"] == "Adaption runs require a JSONL export artifact"


@pytest.mark.asyncio
async def test_adaption_run_requires_configured_credentials(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    monkeypatch.setattr(settings.adaption, "api_key_env", "MISSING_ADAPTION_KEY_FOR_TEST")
    artifact_id = _create_export_artifact(client)

    run_response = client.post(
        "/api/adaption/runs",
        json={"artifact_id": artifact_id, "dataset_name": "argus-awaaz-test"},
    )

    assert run_response.status_code == 400
    assert run_response.json()["detail"] == "Adaption API key is required"


def _create_export_artifact(client: TestClient) -> str:
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
            "corrected_score": 61,
            "corrected_violation_label": "missed_escalation",
            "corrected_escalation_required": True,
        },
    )
    export_response = client.post("/api/datasets/export", json={"format": "jsonl"})
    assert export_response.status_code == 200
    return export_response.json()["artifacts"][0]["id"]


class FakeAdaptionClient:
    def __init__(self) -> None:
        self.uploaded_path = None

    async def create_file_dataset(self, *, name: str, file_format: str):
        return {
            "dataset_id": "dataset-created",
            "status": "pending",
            "upload_instructions": {
                "method": "PUT",
                "url": "https://upload.example.test/presigned",
                "s3_key": "uploads/test.jsonl",
            },
        }

    async def upload_file(self, *, upload_url: str, path):
        self.uploaded_path = path

    async def complete_upload(self, *, name: str, file_format: str, file_path, s3_key: str):
        return {"dataset_id": "dataset-test"}

    async def start_run(self, *, dataset_id: str, estimate: bool = False, max_rows: int | None = None):
        return {"estimate": estimate, "estimatedCreditsConsumed": 10, "estimatedMinutes": 2, "run_id": "run-test"}

    async def get_status(self, *, dataset_id: str):
        return {
            "dataset_id": dataset_id,
            "status": "succeeded",
            "row_count": 1,
            "progress": {"percent": 100, "processed_rows": 1, "total_rows": 1},
            "error": None,
        }

    async def download(self, *, dataset_id: str, file_format: str = "jsonl"):
        return b'{"processed": true}\n'
