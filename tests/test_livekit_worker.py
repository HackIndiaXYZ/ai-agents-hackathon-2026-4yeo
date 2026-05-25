from app.livekit.backend_client import format_qa_result
from app.livekit.backend_client import BackendClient
from app.livekit.worker import _message_text, _metadata_value

import pytest


def test_format_qa_result_for_voice_response():
    result = {
        "final_score": 62,
        "violation_label": "missed_escalation",
        "escalation_required": True,
        "coaching_note": "Escalate the refund dispute.",
    }

    assert format_qa_result(result) == "QA score 62. Label missed_escalation. Escalation required. Escalate the refund dispute."


def test_worker_extracts_message_text_from_list_content():
    message = type("Message", (), {"content": ["hello", "world"]})()

    assert _message_text(message) == "hello world"


def test_worker_extracts_linked_participant_metadata():
    participant = type("Participant", (), {"metadata": '{"voice_session_id": "voice-1", "language": "Hinglish"}'})()
    room_io = type("RoomIO", (), {"linked_participant": participant})()
    session = type("Session", (), {"room_io": room_io})()
    agent = type("Agent", (), {"session": session})()

    assert _metadata_value(agent, "voice_session_id") == "voice-1"
    assert _metadata_value(agent, "language") == "Hinglish"


@pytest.mark.asyncio
async def test_backend_client_runs_agent_tool(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"priority": "P1"}}

    class AsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return Response()

    monkeypatch.setattr("app.livekit.backend_client.httpx.AsyncClient", AsyncClient)

    result = await BackendClient("http://backend/api").run_agent_tool(
        tool_name="escalation_plan",
        input_payload={"domain": "fintech_refund", "violation_label": "privacy_risk"},
    )

    assert result == {"priority": "P1"}
    assert captured["url"] == "http://backend/api/agent-tools/run"
    assert captured["json"]["tool_name"] == "escalation_plan"
