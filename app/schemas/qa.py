from pydantic import BaseModel, Field


class QaSessionCreate(BaseModel):
    workspace_id: str | None = None
    language: str = "Hinglish"
    dialect_or_style: str | None = None
    domain: str = "fintech_refund"
    scenario_type: str | None = None
    is_demo: bool = False


class QaSessionRead(BaseModel):
    id: str
    workspace_id: str | None
    status: str
    language: str
    dialect_or_style: str | None
    domain: str
    scenario_type: str | None
    is_demo: bool
    latest_qa_result_id: str | None

    model_config = {"from_attributes": True}


class TranscriptSubmit(BaseModel):
    transcript: str = Field(min_length=1)
    source: str = "transcript"
    language: str | None = None


class QaResultRead(BaseModel):
    id: str
    qa_session_id: str
    final_score: float
    empathy_score: float
    compliance_score: float
    escalation_score: float
    resolution_score: float
    language_clarity_score: float
    sentiment: str
    urgency: str
    violation_label: str
    escalation_required: bool
    policy_flags: dict
    evidence_spans: list[dict]
    coaching_note: str
    ideal_response: str
    model_metadata: dict

    model_config = {"from_attributes": True}
