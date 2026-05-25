import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.demo import DemoScenario, DemoScenarioRun
from app.schemas.qa import QaSessionCreate, TranscriptSubmit
from app.services.session_service import create_qa_session, submit_transcript


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_scenarios.json"


@lru_cache
def list_demo_scenarios() -> list[DemoScenario]:
    payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return [DemoScenario.model_validate(item) for item in payload]


async def run_demo_scenario(db: AsyncSession, scenario_id: str) -> DemoScenarioRun:
    scenario = _scenario_by_id(scenario_id)
    session = await create_qa_session(
        db,
        QaSessionCreate(
            language=scenario.language,
            domain=scenario.domain,
            scenario_type=scenario.scenario_type,
            is_demo=True,
        ),
    )
    result = await submit_transcript(
        db,
        session,
        TranscriptSubmit(transcript=scenario.transcript, source="demo", language=scenario.language),
    )
    expected_match = (
        result.violation_label == scenario.expected_violation_label
        and result.escalation_required == scenario.expected_escalation_required
    )
    return DemoScenarioRun(scenario=scenario, session=session, result=result, expected_match=expected_match)


def _scenario_by_id(scenario_id: str) -> DemoScenario:
    for scenario in list_demo_scenarios():
        if scenario.id == scenario_id:
            return scenario
    raise ValueError("Demo scenario not found")
