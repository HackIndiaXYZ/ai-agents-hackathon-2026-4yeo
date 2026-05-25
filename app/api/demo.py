from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.demo import DemoScenario, DemoScenarioRun
from app.services.demo_service import list_demo_scenarios, run_demo_scenario

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/scenarios", response_model=list[DemoScenario])
async def read_demo_scenarios():
    return list_demo_scenarios()


@router.post("/scenarios/{scenario_id}/run", response_model=DemoScenarioRun)
async def run_scenario(scenario_id: str, db: AsyncSession = Depends(get_db_session)):
    try:
        return await run_demo_scenario(db, scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
