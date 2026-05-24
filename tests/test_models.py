import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.domain import (
    AdaptionRun,
    DatasetRow,
    ExportArtifact,
    QaResult,
    QaSession,
    ReviewerCorrection,
    TranscriptTurn,
    VoiceSession,
    Workspace,
)


@pytest.mark.asyncio
async def test_backend_entities_can_be_persisted_together():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        workspace = Workspace(name="Demo QA Team")
        session.add(workspace)
        await session.flush()

        qa_session = QaSession(workspace_id=workspace.id, language="Hinglish", domain="fintech_refund")
        session.add(qa_session)
        await session.flush()

        voice_session = VoiceSession(qa_session_id=qa_session.id, room_name="argus-awaaz-test")
        turn = TranscriptTurn(
            qa_session_id=qa_session.id,
            voice_session_id=voice_session.id,
            role="customer",
            language="Hinglish",
            content="Mera refund abhi tak nahi aaya, please escalate this.",
        )
        session.add_all([voice_session, turn])
        await session.flush()

        result = QaResult(
            qa_session_id=qa_session.id,
            final_score=62,
            empathy_score=70,
            compliance_score=80,
            escalation_score=30,
            resolution_score=55,
            language_clarity_score=75,
            sentiment="frustrated",
            urgency="high",
            violation_label="missed_escalation",
            escalation_required=True,
            policy_flags={"refund_dispute": True},
            evidence_spans=[{"text": "please escalate this"}],
            coaching_note="Escalate the refund dispute and acknowledge the delay.",
            ideal_response="I understand the delay. I will escalate this refund dispute now.",
        )
        session.add(result)
        await session.flush()

        correction = ReviewerCorrection(
            qa_session_id=qa_session.id,
            qa_result_id=result.id,
            original_result={"violation_label": result.violation_label},
            corrected_score=58,
            corrected_violation_label="refund_dispute",
            corrected_escalation_required=True,
        )
        session.add(correction)
        await session.flush()

        dataset_row = DatasetRow(
            source_type="correction",
            qa_session_id=qa_session.id,
            correction_id=correction.id,
            language="Hinglish",
            domain="fintech_refund",
            prompt="Evaluate this support call.",
            completion="Escalation required for refund dispute.",
            context="Refund dispute policy.",
            chat_payload={"messages": [{"role": "customer", "content": turn.content}]},
            labels={"violation_label": "refund_dispute"},
        )
        session.add(dataset_row)
        await session.flush()
        correction.dataset_row_id = dataset_row.id

        adaption_run = AdaptionRun(dataset_id=dataset_row.id, run_id="run-test", status="created")
        export = ExportArtifact(artifact_type="jsonl", path="artifacts/datasets/test.jsonl", row_count=1)
        session.add_all([adaption_run, export])
        await session.commit()

        assert workspace.id
        assert qa_session.id
        assert result.escalation_required is True
        assert correction.dataset_row_id == dataset_row.id
        assert adaption_run.run_id == "run-test"
        assert export.row_count == 1

    await engine.dispose()
