from pydantic import BaseModel

from app.schemas.qa import QaResultRead, QaSessionRead


class DemoScenario(BaseModel):
    id: str
    title: str
    language: str
    domain: str
    scenario_type: str
    expected_violation_label: str
    expected_escalation_required: bool
    transcript: str


class DemoScenarioRun(BaseModel):
    scenario: DemoScenario
    session: QaSessionRead
    result: QaResultRead
    expected_match: bool
