from app.livekit.backend_client import format_qa_result
from app.livekit.worker import _message_text, _metadata_value


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
