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

Inspect and run backend agent tools:

```bash
curl http://localhost:8000/api/agent-tools
curl -X POST http://localhost:8000/api/agent-tools/run \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"risk_scan","input":{"domain":"fintech_refund","language":"Hinglish","transcript":"Customer asks for escalation after a refund delay."}}'
```

Ingest voice events:

```bash
curl -X POST http://localhost:8000/api/voice/events \
  -H "Content-Type: application/json" \
  -d '{"voice_session_id":"<voice-session-id>","event_type":"partial_transcript","transcript":"Customer refund stuck hai"}'

curl -X POST http://localhost:8000/api/voice/events \
  -H "Content-Type: application/json" \
  -d '{"voice_session_id":"<voice-session-id>","event_type":"final_transcript","transcript":"Customer refund stuck hai, please escalate this complaint."}'

curl -X POST http://localhost:8000/api/voice/events \
  -H "Content-Type: application/json" \
  -d '{"voice_session_id":"<voice-session-id>","event_type":"interruption","provider_metadata":{"reason":"barge_in"}}'
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
