from dataclasses import dataclass


@dataclass(frozen=True)
class QaDecision:
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


def score_support_transcript(*, transcript: str, language: str, domain: str) -> QaDecision:
    normalized = transcript.lower()
    flags: dict[str, bool] = {}
    evidence: list[dict] = []

    refund_terms = ["refund", "paise", "paisa", "amount", "transaction", "payment", "failed"]
    escalation_terms = ["escalate", "senior", "manager", "complaint", "legal", "rbi", "ombudsman"]
    privacy_terms = ["otp", "password", "pin", "cvv", "card number", "account number"]
    anger_terms = ["angry", "gussa", "frustrated", "bekaar", "worst", "bad service", "not acceptable"]

    refund_dispute = _contains_any(normalized, refund_terms)
    escalation_cue = _contains_any(normalized, escalation_terms)
    privacy_risk = _contains_any(normalized, privacy_terms)
    angry_customer = _contains_any(normalized, anger_terms)

    if refund_dispute:
        flags["refund_dispute"] = True
        evidence.append({"label": "refund_dispute", "text": _first_match(transcript, refund_terms)})
    if escalation_cue:
        flags["escalation_cue"] = True
        evidence.append({"label": "escalation_cue", "text": _first_match(transcript, escalation_terms)})
    if privacy_risk:
        flags["privacy_risk"] = True
        evidence.append({"label": "privacy_risk", "text": _first_match(transcript, privacy_terms)})
    if angry_customer:
        flags["angry_customer"] = True
        evidence.append({"label": "angry_customer", "text": _first_match(transcript, anger_terms)})

    escalation_required = escalation_cue or privacy_risk or (refund_dispute and angry_customer)
    violation_label = _violation_label(
        privacy_risk=privacy_risk,
        escalation_required=escalation_required,
        refund_dispute=refund_dispute,
        angry_customer=angry_customer,
    )
    urgency = "high" if escalation_required or angry_customer else "medium" if refund_dispute else "low"
    sentiment = "frustrated" if angry_customer or refund_dispute else "calm"

    compliance_score = 45 if privacy_risk else 70 if escalation_required else 88
    escalation_score = 35 if escalation_required else 86
    resolution_score = 55 if refund_dispute else 82
    empathy_score = 64 if angry_customer else 78
    language_clarity_score = 76 if language.lower() in {"hinglish", "hindi", "indian english"} else 68
    final_score = round(
        empathy_score * 0.2
        + compliance_score * 0.25
        + escalation_score * 0.25
        + resolution_score * 0.2
        + language_clarity_score * 0.1,
        2,
    )
    recommended_tool = "escalation_plan" if escalation_required else "policy_lookup"

    return QaDecision(
        final_score=final_score,
        empathy_score=empathy_score,
        compliance_score=compliance_score,
        escalation_score=escalation_score,
        resolution_score=resolution_score,
        language_clarity_score=language_clarity_score,
        sentiment=sentiment,
        urgency=urgency,
        violation_label=violation_label,
        escalation_required=escalation_required,
        policy_flags=flags,
        evidence_spans=evidence,
        coaching_note=_coaching_note(violation_label),
        ideal_response=_ideal_response(violation_label, domain),
        model_metadata={
            "scoring_mode": "deterministic_policy",
            "language": language,
            "domain": domain,
            "recommended_tool": recommended_tool,
            "recommended_action": _recommended_action(violation_label, escalation_required),
            "score_reason": _score_reason(
                privacy_risk=privacy_risk,
                escalation_cue=escalation_cue,
                refund_dispute=refund_dispute,
                angry_customer=angry_customer,
            ),
            "evidence_count": len(evidence),
        },
    )


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _first_match(original: str, terms: list[str]) -> str:
    lowered = original.lower()
    for term in terms:
        if term in lowered:
            return term
    return ""


def _violation_label(*, privacy_risk: bool, escalation_required: bool, refund_dispute: bool, angry_customer: bool) -> str:
    if privacy_risk:
        return "privacy_risk"
    if escalation_required:
        return "missed_escalation"
    if refund_dispute:
        return "refund_dispute"
    if angry_customer:
        return "incomplete_resolution"
    return "good_handling"


def _coaching_note(label: str) -> str:
    notes = {
        "privacy_risk": "Do not request sensitive credentials. Verify identity through approved support steps and escalate immediately.",
        "missed_escalation": "Acknowledge the concern, summarize the issue, and move the case to the escalation path with clear next steps.",
        "refund_dispute": "Confirm the refund context, share the expected process, and set a clear follow-up timeline.",
        "incomplete_resolution": "Show empathy first, then ask one clarifying question and provide a concrete next action.",
        "good_handling": "The interaction is handled cleanly. Maintain the same clarity and policy alignment.",
    }
    return notes[label]


def _ideal_response(label: str, domain: str) -> str:
    if label == "privacy_risk":
        return "I cannot ask for OTP, PIN, password, or card security details. I will verify you through approved steps and escalate this safely."
    if label == "missed_escalation":
        return "I understand this has become urgent. I am escalating the case now and will share the next update timeline."
    if label == "refund_dispute":
        return "I understand the refund delay. I will check the transaction status, confirm the expected timeline, and create a follow-up note."
    if label == "incomplete_resolution":
        return "I understand the frustration. Let me confirm the issue once and then share the next action clearly."
    return f"This {domain.replace('_', ' ')} support interaction is clear, policy-aligned, and ready for closure."


def _recommended_action(label: str, escalation_required: bool) -> str:
    if label == "privacy_risk":
        return "stop_sensitive_data_collection_and_escalate"
    if escalation_required:
        return "create_human_handoff"
    if label == "refund_dispute":
        return "verify_refund_status_and_share_timeline"
    if label == "incomplete_resolution":
        return "ask_clarifying_question_and_confirm_next_step"
    return "accept_result"


def _score_reason(*, privacy_risk: bool, escalation_cue: bool, refund_dispute: bool, angry_customer: bool) -> str:
    reasons = []
    if privacy_risk:
        reasons.append("sensitive credential risk")
    if escalation_cue:
        reasons.append("explicit escalation cue")
    if refund_dispute:
        reasons.append("refund or payment dispute")
    if angry_customer:
        reasons.append("frustrated customer signal")
    if not reasons:
        return "No major risk signal was detected."
    return "Detected " + ", ".join(reasons) + "."
