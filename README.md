# Argus Awaaz QA

Multilingual support-call QA backend for the AI Agents Hackathon 2026.

## Local Backend

```bash
cp .env.example .env
docker compose up --build
```

API health:

```text
http://localhost:8000/api/health
```

Run tests:

```bash
python -m pytest -q
```

Load the synthetic showcase dataset after the database is migrated:

```bash
python scripts/load_seed_dataset.py
```

Or load it through the API:

```bash
curl -X POST http://localhost:8000/api/datasets/seed/load
```

Run the backend golden-path smoke check after the API is up:

```bash
python scripts/smoke_backend.py --api-base-url http://localhost:8000/api
```

The smoke check runs:

```text
health -> demo scenario -> QA result -> correction -> dataset export -> analytics
```

To include a real Adaption run, configure `ADAPTION_API_KEY` and run:

```bash
python scripts/smoke_backend.py --include-adaption
```
