"""initial backend tables

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260525_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "qa_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("dialect_or_style", sa.String(), nullable=True),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("scenario_type", sa.String(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("latest_qa_result_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qa_sessions_workspace_id", "qa_sessions", ["workspace_id"])
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("qa_session_id", sa.String(), nullable=True),
        sa.Column("room_name", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_voice_sessions_qa_session_id", "voice_sessions", ["qa_session_id"])
    op.create_table(
        "transcript_turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("qa_session_id", sa.String(), nullable=False),
        sa.Column("voice_session_id", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transcript_turns_qa_session_id", "transcript_turns", ["qa_session_id"])
    op.create_index("ix_transcript_turns_voice_session_id", "transcript_turns", ["voice_session_id"])
    op.create_table(
        "qa_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("qa_session_id", sa.String(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("empathy_score", sa.Float(), nullable=False),
        sa.Column("compliance_score", sa.Float(), nullable=False),
        sa.Column("escalation_score", sa.Float(), nullable=False),
        sa.Column("resolution_score", sa.Float(), nullable=False),
        sa.Column("language_clarity_score", sa.Float(), nullable=False),
        sa.Column("sentiment", sa.String(), nullable=False),
        sa.Column("urgency", sa.String(), nullable=False),
        sa.Column("violation_label", sa.String(), nullable=False),
        sa.Column("escalation_required", sa.Boolean(), nullable=False),
        sa.Column("policy_flags", sa.JSON(), nullable=False),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        sa.Column("coaching_note", sa.Text(), nullable=False),
        sa.Column("ideal_response", sa.Text(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qa_results_qa_session_id", "qa_results", ["qa_session_id"])
    op.create_table(
        "reviewer_corrections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("qa_session_id", sa.String(), nullable=False),
        sa.Column("qa_result_id", sa.String(), nullable=False),
        sa.Column("dataset_row_id", sa.String(), nullable=True),
        sa.Column("original_result", sa.JSON(), nullable=False),
        sa.Column("corrected_transcript", sa.Text(), nullable=True),
        sa.Column("corrected_score", sa.Float(), nullable=True),
        sa.Column("corrected_violation_label", sa.String(), nullable=True),
        sa.Column("corrected_escalation_required", sa.Boolean(), nullable=True),
        sa.Column("corrected_coaching_note", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reviewer_corrections_qa_session_id", "reviewer_corrections", ["qa_session_id"])
    op.create_index("ix_reviewer_corrections_qa_result_id", "reviewer_corrections", ["qa_result_id"])
    op.create_table(
        "dataset_rows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("qa_session_id", sa.String(), nullable=True),
        sa.Column("correction_id", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("completion", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("chat_payload", sa.JSON(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("export_status", sa.String(), nullable=False),
        sa.Column("adaption_dataset_id", sa.String(), nullable=True),
        sa.Column("adaption_run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dataset_rows_qa_session_id", "dataset_rows", ["qa_session_id"])
    op.create_index("ix_dataset_rows_correction_id", "dataset_rows", ["correction_id"])
    op.create_table(
        "adaption_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("exported_file_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("export_artifacts")
    op.drop_table("adaption_runs")
    op.drop_index("ix_dataset_rows_correction_id", table_name="dataset_rows")
    op.drop_index("ix_dataset_rows_qa_session_id", table_name="dataset_rows")
    op.drop_table("dataset_rows")
    op.drop_index("ix_reviewer_corrections_qa_result_id", table_name="reviewer_corrections")
    op.drop_index("ix_reviewer_corrections_qa_session_id", table_name="reviewer_corrections")
    op.drop_table("reviewer_corrections")
    op.drop_index("ix_qa_results_qa_session_id", table_name="qa_results")
    op.drop_table("qa_results")
    op.drop_index("ix_transcript_turns_voice_session_id", table_name="transcript_turns")
    op.drop_index("ix_transcript_turns_qa_session_id", table_name="transcript_turns")
    op.drop_table("transcript_turns")
    op.drop_index("ix_voice_sessions_qa_session_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
    op.drop_index("ix_qa_sessions_workspace_id", table_name="qa_sessions")
    op.drop_table("qa_sessions")
    op.drop_table("workspaces")
