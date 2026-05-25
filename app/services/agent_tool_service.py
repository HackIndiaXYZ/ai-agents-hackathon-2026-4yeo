import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.domain import DatasetRow, QaResult, QaSession, ReviewerCorrection, TranscriptTurn
from app.schemas.agent_tools import AgentToolDefinition, AgentToolRunRequest, AgentToolRunResponse
from app.services.qa_service import score_support_transcript


def list_agent_tools() -> list[AgentToolDefinition]:
    settings = get_settings()
    return [
        AgentToolDefinition(
            name="policy_lookup",
            description="Return domain-specific support QA policy, required actions, prohibited actions, and escalation triggers.",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "risk_label": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["domain"],
            },
            output_schema={"type": "object", "required": ["domain", "summary", "required_actions", "prohibited_actions"]},
            tags=settings.agent_tools.catalog_tags,
        ),
        AgentToolDefinition(
            name="risk_scan",
            description="Scan a support transcript for QA score, policy flags, evidence spans, escalation need, and the next recommended tool.",
            input_schema={
                "type": "object",
                "properties": {
                    "transcript": {"type": "string"},
                    "language": {"type": "string"},
                    "domain": {"type": "string"},
                },
                "required": ["transcript", "domain"],
            },
            output_schema={"type": "object", "required": ["final_score", "violation_label", "escalation_required"]},
            tags=settings.agent_tools.catalog_tags,
        ),
        AgentToolDefinition(
            name="escalation_plan",
            description="Build a structured human handoff plan for urgent, risky, or low-scoring support interactions.",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "violation_label": {"type": "string"},
                    "urgency": {"type": "string"},
                    "final_score": {"type": "number"},
                    "transcript": {"type": "string"},
                },
                "required": ["domain", "violation_label"],
            },
            output_schema={"type": "object", "required": ["priority", "actions", "handoff_payload"]},
            tags=settings.agent_tools.catalog_tags,
        ),
        AgentToolDefinition(
            name="dataset_readiness",
            description="Report whether dataset rows are ready for export and adaptive-data ingestion.",
            input_schema={"type": "object", "properties": {"version": {"type": "string"}}},
            output_schema={"type": "object", "required": ["row_count", "export_ready", "missing_fields"]},
            tags=settings.agent_tools.catalog_tags,
        ),
        AgentToolDefinition(
            name="session_summary",
            description="Summarize one QA session with transcript turns, latest result, corrections, and recommended next action.",
            input_schema={"type": "object", "properties": {"qa_session_id": {"type": "string"}}, "required": ["qa_session_id"]},
            output_schema={"type": "object", "required": ["qa_session_id", "status", "recommended_next_action"]},
            tags=settings.agent_tools.catalog_tags,
        ),
    ]


async def run_agent_tool(db: AsyncSession, payload: AgentToolRunRequest) -> AgentToolRunResponse:
    tool_name = payload.tool_name.strip()
    if tool_name == "policy_lookup":
        result = policy_lookup(payload.input)
    elif tool_name == "risk_scan":
        result = risk_scan(payload.input)
    elif tool_name == "escalation_plan":
        result = escalation_plan(payload.input)
    elif tool_name == "dataset_readiness":
        result = await dataset_readiness(db, payload.input)
    elif tool_name == "session_summary":
        result = await session_summary(db, payload.input)
    else:
        raise ValueError(f"Unsupported agent tool: {payload.tool_name}")
    return AgentToolRunResponse(tool_name=tool_name, result=result)


def policy_lookup(input_payload: dict[str, Any]) -> dict[str, Any]:
    domain = _required_str(input_payload, "domain")
    risk_label = str(input_payload.get("risk_label") or "").strip()
    language = str(input_payload.get("language") or "").strip() or "Hinglish"
    policies = _load_policies()
    default_policy = policies["default"]
    domain_policy = policies.get(domain, default_policy)
    required_actions = _merged_list(default_policy["required_actions"], domain_policy["required_actions"])
    prohibited_actions = _merged_list(default_policy["prohibited_actions"], domain_policy["prohibited_actions"])
    escalation_triggers = _merged_list(default_policy["escalation_triggers"], domain_policy["escalation_triggers"])

    return {
        "domain": domain,
        "language": language,
        "risk_label": risk_label or None,
        "summary": domain_policy["summary"],
        "required_actions": required_actions,
        "prohibited_actions": prohibited_actions,
        "escalation_triggers": escalation_triggers,
        "review_instruction": _review_instruction(risk_label),
        "dataset_context": {
            "policy_domain": domain,
            "risk_label": risk_label or "general",
            "language": language,
        },
    }


def risk_scan(input_payload: dict[str, Any]) -> dict[str, Any]:
    transcript = _required_str(input_payload, "transcript")
    domain = _required_str(input_payload, "domain")
    language = str(input_payload.get("language") or "").strip() or "Hinglish"
    decision = score_support_transcript(transcript=transcript, language=language, domain=domain)
    next_tool = "escalation_plan" if decision.escalation_required else "policy_lookup"

    return {
        "final_score": decision.final_score,
        "score_breakdown": {
            "empathy": decision.empathy_score,
            "compliance": decision.compliance_score,
            "escalation": decision.escalation_score,
            "resolution": decision.resolution_score,
            "language_clarity": decision.language_clarity_score,
        },
        "sentiment": decision.sentiment,
        "urgency": decision.urgency,
        "violation_label": decision.violation_label,
        "escalation_required": decision.escalation_required,
        "policy_flags": decision.policy_flags,
        "evidence_spans": decision.evidence_spans,
        "coaching_note": decision.coaching_note,
        "ideal_response": decision.ideal_response,
        "recommended_next_tool": next_tool,
    }


def escalation_plan(input_payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    domain = _required_str(input_payload, "domain")
    violation_label = _required_str(input_payload, "violation_label")
    urgency = str(input_payload.get("urgency") or "").strip() or "medium"
    final_score = _optional_float(input_payload.get("final_score"))
    transcript = str(input_payload.get("transcript") or "").strip()
    policy = policy_lookup({"domain": domain, "risk_label": violation_label})
    priority = _priority(
        label=violation_label,
        urgency=urgency,
        final_score=final_score,
        threshold=settings.agent_tools.escalation_score_threshold,
        high_urgency_labels=settings.agent_tools.high_urgency_labels,
    )
    actions = _escalation_actions(priority, violation_label, policy["required_actions"])

    return {
        "priority": priority,
        "domain": domain,
        "violation_label": violation_label,
        "urgency": urgency,
        "actions": actions,
        "handoff_payload": {
            "queue": "qa_escalation",
            "priority": priority,
            "reason": violation_label,
            "domain": domain,
            "customer_signal": _excerpt(transcript),
        },
        "reviewer_note": _reviewer_note(priority, violation_label),
    }


async def dataset_readiness(db: AsyncSession, input_payload: dict[str, Any]) -> dict[str, Any]:
    version = str(input_payload.get("version") or "").strip() or None
    query = select(DatasetRow).order_by(DatasetRow.created_at)
    if version:
        query = query.where(DatasetRow.version == version)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    missing_fields = _missing_dataset_fields(rows)
    exported_count = sum(1 for row in rows if row.export_status == "exported")
    labels = _count_by(rows, lambda row: str(row.labels.get("violation_label", "unknown")))
    languages = _count_by(rows, lambda row: row.language)
    domains = _count_by(rows, lambda row: row.domain)
    export_ready = bool(rows) and not missing_fields

    return {
        "version": version,
        "row_count": len(rows),
        "exported_count": exported_count,
        "pending_count": len(rows) - exported_count,
        "export_ready": export_ready,
        "missing_fields": missing_fields,
        "rows_by_language": languages,
        "rows_by_domain": domains,
        "rows_by_label": labels,
        "next_action": "export_dataset" if export_ready else "load_or_fix_dataset_rows",
    }


async def session_summary(db: AsyncSession, input_payload: dict[str, Any]) -> dict[str, Any]:
    session_id = _required_str(input_payload, "qa_session_id")
    session = await db.get(QaSession, session_id)
    if not session:
        raise ValueError("QA session not found")
    turns = await _session_turns(db, session_id)
    latest_result = await _latest_result(db, session)
    corrections_count = await db.scalar(
        select(func.count()).select_from(ReviewerCorrection).where(ReviewerCorrection.qa_session_id == session_id)
    )
    result_payload = _result_payload(latest_result)
    recommended_next_action = _session_next_action(turns=turns, result=latest_result, corrections_count=corrections_count or 0)

    return {
        "qa_session_id": session.id,
        "status": session.status,
        "language": session.language,
        "domain": session.domain,
        "turn_count": len(turns),
        "latest_transcript_excerpt": _excerpt(turns[-1].content if turns else ""),
        "latest_result": result_payload,
        "corrections_count": corrections_count or 0,
        "recommended_next_action": recommended_next_action,
    }


@lru_cache
def _load_policies() -> dict[str, Any]:
    path = Path(get_settings().agent_tools.policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "default" not in payload:
        raise ValueError("Policy file must contain a default policy")
    return payload


def _required_str(input_payload: dict[str, Any], field: str) -> str:
    value = str(input_payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("final_score must be numeric") from exc


def _merged_list(base: list[str], override: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*override, *base]:
        if item not in merged:
            merged.append(item)
    return merged


def _review_instruction(risk_label: str) -> str:
    if risk_label == "privacy_risk":
        return "Prioritize credential safety, mark compliance risk, and escalate immediately."
    if risk_label == "missed_escalation":
        return "Check whether the agent acknowledged escalation intent and created a clear handoff."
    if risk_label == "refund_dispute":
        return "Check whether refund context, timeline, and next follow-up were clearly provided."
    return "Review the call for empathy, policy alignment, escalation need, and concrete resolution."


def _priority(*, label: str, urgency: str, final_score: float | None, threshold: int, high_urgency_labels: list[str]) -> str:
    if label in high_urgency_labels or urgency == "high":
        return "P1"
    if final_score is not None and final_score < threshold:
        return "P2"
    if label in {"refund_dispute", "incomplete_resolution"}:
        return "P2"
    return "P3"


def _escalation_actions(priority: str, label: str, required_actions: list[str]) -> list[str]:
    actions = [
        "Create a reviewer-visible handoff note.",
        "Attach evidence spans or transcript excerpt.",
        "State the policy reason for escalation.",
    ]
    if priority == "P1":
        actions.insert(0, "Route to a senior reviewer before closing the session.")
    if label == "privacy_risk":
        actions.insert(0, "Stop credential collection and use approved verification only.")
    return _merged_list(actions, required_actions[:3])


def _reviewer_note(priority: str, label: str) -> str:
    return f"{priority} handoff recommended because the interaction is tagged as {label}."


def _excerpt(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


async def _session_turns(db: AsyncSession, session_id: str) -> list[TranscriptTurn]:
    result = await db.execute(select(TranscriptTurn).where(TranscriptTurn.qa_session_id == session_id).order_by(TranscriptTurn.created_at))
    return list(result.scalars().all())


async def _latest_result(db: AsyncSession, session: QaSession) -> QaResult | None:
    if not session.latest_qa_result_id:
        return None
    return await db.get(QaResult, session.latest_qa_result_id)


def _result_payload(result: QaResult | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "id": result.id,
        "final_score": result.final_score,
        "violation_label": result.violation_label,
        "escalation_required": result.escalation_required,
        "sentiment": result.sentiment,
        "urgency": result.urgency,
        "coaching_note": result.coaching_note,
    }


def _session_next_action(*, turns: list[TranscriptTurn], result: QaResult | None, corrections_count: int) -> str:
    if not turns:
        return "capture_transcript"
    if not result:
        return "run_risk_scan"
    if result.escalation_required and corrections_count == 0:
        return "review_escalation"
    if corrections_count == 0:
        return "review_or_accept_result"
    return "dataset_ready"


def _missing_dataset_fields(rows: list[DatasetRow]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for row in rows:
        checks = {
            "prompt": row.prompt,
            "completion": row.completion,
            "context": row.context,
            "chat_payload": row.chat_payload,
            "labels": row.labels,
        }
        for field, value in checks.items():
            if value in ("", None, {}, []):
                missing.append({"row_id": row.id, "field": field})
    return missing


def _count_by(rows: list[DatasetRow], key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = key_fn(row)
        counts[key] = counts.get(key, 0) + 1
    return counts
