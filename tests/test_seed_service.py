import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models.domain import DatasetRow
from app.schemas.qa import DatasetExportRequest
from app.services.dataset_service import export_dataset_rows
from app.services.seed_service import load_seed_dataset_rows


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


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
async def test_seed_loader_inserts_dataset_rows_idempotently(db_session):
    first_result = await load_seed_dataset_rows(db_session)
    second_result = await load_seed_dataset_rows(db_session)

    assert first_result == {"inserted": 50, "skipped": 0, "total": 50}
    assert second_result == {"inserted": 0, "skipped": 50, "total": 50}

    count = await db_session.scalar(select(func.count()).select_from(DatasetRow))
    assert count == 50

    result = await db_session.execute(select(DatasetRow).where(DatasetRow.id == "seed-001"))
    row = result.scalar_one()
    assert row.source_type == "seed"
    assert row.language == "Hinglish"
    assert row.export_status == "pending"
    assert row.chat_payload["messages"][0]["role"] == "conversation"
    assert row.labels["violation_label"] == "missed_escalation"


@pytest.mark.asyncio
async def test_seed_rows_can_be_exported_as_dataset_package(db_session, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings.adaption, "export_dir", str(tmp_path))
    await load_seed_dataset_rows(db_session)

    response = await export_dataset_rows(db_session, DatasetExportRequest(format="all"))

    assert response.row_count == 50
    assert response.formats == ["jsonl", "csv", "mapping", "hf_card", "kaggle_metadata"]
    assert len(response.artifacts) == 5

    artifacts = {artifact.artifact_type: artifact for artifact in response.artifacts}
    jsonl_path = tmp_path / _filename(artifacts["jsonl"].path)
    mapping_path = tmp_path / _filename(artifacts["mapping"].path)

    exported_rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(exported_rows) == 50
    assert {row["source_type"] for row in exported_rows} == {"seed"}
    assert {"Hinglish", "Hindi", "Indian English"}.issubset({row["language"] for row in exported_rows})

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert mapping["row_count"] == 50
    assert mapping["columns"]["completion"] == "completion"

    statuses = await db_session.scalars(select(DatasetRow.export_status))
    assert set(statuses.all()) == {"exported"}


@pytest.mark.asyncio
async def test_seed_loader_api_is_idempotent(client):
    first_response = client.post("/api/datasets/seed/load")
    second_response = client.post("/api/datasets/seed/load")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == {"inserted": 50, "skipped": 0, "total": 50}
    assert second_response.json() == {"inserted": 0, "skipped": 50, "total": 50}

    rows_response = client.get("/api/datasets/rows")
    assert rows_response.status_code == 200
    assert len(rows_response.json()) == 50


def _filename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
