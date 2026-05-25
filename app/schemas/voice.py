from pydantic import BaseModel, Field


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
    transcript: str = Field(min_length=1)
    language: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider_metadata: dict = Field(default_factory=dict)


class VoiceSessionRead(BaseModel):
    id: str
    qa_session_id: str | None
    room_name: str
    status: str
    metadata_json: dict

    model_config = {"from_attributes": True}
