from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.qa import QaResultRead


class VoiceConnectRequest(BaseModel):
    qa_session_id: str | None = None
    workspace_id: str | None = None
    language: str = "Hinglish"
    domain: str = "fintech_refund"
    participant_identity: str = "qa-reviewer"


class VoiceConnectResponse(BaseModel):
    token: str
    livekit_url: str
    room_name: str
    voice_session_id: str
    qa_session_id: str


class VoiceEventRequest(BaseModel):
    voice_session_id: str
    event_type: Literal["partial_transcript", "final_transcript", "interruption", "agent_state", "metrics"] = "final_transcript"
    transcript: str | None = None
    role: Literal["customer", "agent", "system"] = "customer"
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    turn_index: int | None = Field(default=None, ge=0)
    agent_state: str | None = None
    metrics: dict = Field(default_factory=dict)
    provider_metadata: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None


class VoiceEventResponse(BaseModel):
    voice_session_id: str
    qa_session_id: str
    event_type: str
    accepted: bool
    turn_id: str | None = None
    qa_result: QaResultRead | None = None
    recommended_next_action: str
    voice_state: dict


class VoiceSessionRead(BaseModel):
    id: str
    qa_session_id: str | None
    room_name: str
    status: str
    metadata_json: dict

    model_config = {"from_attributes": True}
