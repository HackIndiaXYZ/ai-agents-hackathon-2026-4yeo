from __future__ import annotations

from typing import Any
import uuid

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    tier: Mapped[str] = mapped_column(String, default="standard", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class QaSession(TimestampMixin, Base):
    __tablename__ = "qa_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    workspace_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    language: Mapped[str] = mapped_column(String, default="Hinglish", nullable=False)
    dialect_or_style: Mapped[str | None] = mapped_column(String, nullable=True)
    domain: Mapped[str] = mapped_column(String, default="fintech_refund", nullable=False)
    scenario_type: Mapped[str | None] = mapped_column(String, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latest_qa_result_id: Mapped[str | None] = mapped_column(String, nullable=True)


class VoiceSession(TimestampMixin, Base):
    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    qa_session_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    room_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="created", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class TranscriptTurn(TimestampMixin, Base):
    __tablename__ = "transcript_turns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    qa_session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    voice_session_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, default="transcript", nullable=False)
    language: Mapped[str] = mapped_column(String, default="Hinglish", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class QaResult(TimestampMixin, Base):
    __tablename__ = "qa_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    qa_session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    empathy_score: Mapped[float] = mapped_column(Float, nullable=False)
    compliance_score: Mapped[float] = mapped_column(Float, nullable=False)
    escalation_score: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_score: Mapped[float] = mapped_column(Float, nullable=False)
    language_clarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment: Mapped[str] = mapped_column(String, nullable=False)
    urgency: Mapped[str] = mapped_column(String, nullable=False)
    violation_label: Mapped[str] = mapped_column(String, nullable=False)
    escalation_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_flags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_spans: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    coaching_note: Mapped[str] = mapped_column(Text, nullable=False)
    ideal_response: Mapped[str] = mapped_column(Text, nullable=False)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ReviewerCorrection(TimestampMixin, Base):
    __tablename__ = "reviewer_corrections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    qa_session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    qa_result_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    dataset_row_id: Mapped[str | None] = mapped_column(String, nullable=True)
    original_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    corrected_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_violation_label: Mapped[str | None] = mapped_column(String, nullable=True)
    corrected_escalation_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    corrected_coaching_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DatasetRow(TimestampMixin, Base):
    __tablename__ = "dataset_rows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    qa_session_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    correction_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    language: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    completion: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    chat_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[str] = mapped_column(String, default="v0", nullable=False)
    export_status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    adaption_dataset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    adaption_run_id: Mapped[str | None] = mapped_column(String, nullable=True)


class AdaptionRun(TimestampMixin, Base):
    __tablename__ = "adaption_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String, default="created", nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    exported_file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExportArtifact(TimestampMixin, Base):
    __tablename__ = "export_artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
