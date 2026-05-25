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


class ReviewerCorrectionCreate(BaseModel):
    corrected_transcript: str | None = None
    corrected_score: float | None = Field(default=None, ge=0, le=100)
    corrected_violation_label: str | None = None
    corrected_escalation_required: bool | None = None
    corrected_coaching_note: str | None = None
    reviewer_note: str | None = None
    accepted: bool = True


class ReviewerCorrectionRead(BaseModel):
    id: str
    qa_session_id: str
    qa_result_id: str
    dataset_row_id: str | None
    original_result: dict
    corrected_transcript: str | None
    corrected_score: float | None
    corrected_violation_label: str | None
    corrected_escalation_required: bool | None
    corrected_coaching_note: str | None
    reviewer_note: str | None
    accepted: bool

    model_config = {"from_attributes": True}


class DatasetRowRead(BaseModel):
    id: str
    source_type: str
    qa_session_id: str | None
    correction_id: str | None
    language: str
    domain: str
    prompt: str
    completion: str
    context: str
    chat_payload: dict
    labels: dict
    version: str
    export_status: str
    adaption_dataset_id: str | None
    adaption_run_id: str | None

    model_config = {"from_attributes": True}


class DatasetExportRequest(BaseModel):
    format: str = "jsonl"
    version: str | None = None


class ExportArtifactRead(BaseModel):
    id: str
    artifact_type: str
    path: str
    row_count: int
    metadata_json: dict

    model_config = {"from_attributes": True}


class DatasetExportResponse(BaseModel):
    artifacts: list[ExportArtifactRead]
    row_count: int
    formats: list[str]


class SeedLoadResponse(BaseModel):
    inserted: int
    skipped: int
    total: int
