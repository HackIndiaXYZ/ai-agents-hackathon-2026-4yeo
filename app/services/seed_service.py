import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import DatasetRow


DEFAULT_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_dataset_rows.jsonl"


async def load_seed_dataset_rows(db: AsyncSession, path: Path = DEFAULT_SEED_PATH) -> dict[str, int]:
    rows = _read_seed_rows(path)
    inserted = 0
    skipped = 0
    for row in rows:
        _validate_seed_row(row)
        existing = await _existing_seed_row(db, row["id"])
        if existing:
            skipped += 1
            continue
        db.add(
            DatasetRow(
                id=row["id"],
                source_type="seed",
                language=row["language"],
                domain=row["domain"],
                prompt=row["prompt"],
                completion=row["completion"],
                context=row["context"],
                chat_payload=row["chat_payload"],
                labels=row["labels"],
                version=row.get("version", "v0"),
                export_status="pending",
            )
        )
        inserted += 1
    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total": len(rows)}


def _read_seed_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Seed dataset file not found: {path}")
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Seed row at line {line_number} must be an object")
        rows.append(row)
    return rows


def _validate_seed_row(row: dict[str, Any]) -> None:
    required = ["id", "language", "domain", "prompt", "completion", "context", "chat_payload", "labels"]
    missing = [field for field in required if field not in row or row[field] in ("", None, {}, [])]
    if missing:
        raise ValueError(f"Seed row {row.get('id', '<unknown>')} is missing required fields: {', '.join(missing)}")
    if row.get("source_type") != "seed":
        raise ValueError(f"Seed row {row['id']} must use source_type=seed")
    if not isinstance(row["chat_payload"], dict):
        raise ValueError(f"Seed row {row['id']} chat_payload must be an object")
    if not isinstance(row["labels"], dict):
        raise ValueError(f"Seed row {row['id']} labels must be an object")


async def _existing_seed_row(db: AsyncSession, row_id: str) -> DatasetRow | None:
    result = await db.execute(select(DatasetRow).where(DatasetRow.id == row_id))
    return result.scalar_one_or_none()
