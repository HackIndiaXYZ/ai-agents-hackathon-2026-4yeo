from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import AsyncSessionLocal
from app.services.seed_service import DEFAULT_SEED_PATH, load_seed_dataset_rows


async def _run(path: Path) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        return await load_seed_dataset_rows(session, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load synthetic seed dataset rows into the backend database.")
    parser.add_argument("--path", default=str(DEFAULT_SEED_PATH))
    args = parser.parse_args()
    result = asyncio.run(_run(Path(args.path)))
    print(f"seed rows: inserted={result['inserted']} skipped={result['skipped']} total={result['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
