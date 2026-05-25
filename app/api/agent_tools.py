from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.agent_tools import AgentToolDefinition, AgentToolRunRequest, AgentToolRunResponse
from app.services.agent_tool_service import list_agent_tools, run_agent_tool

router = APIRouter(prefix="/agent-tools", tags=["agent-tools"])


@router.get("", response_model=list[AgentToolDefinition])
async def read_agent_tools():
    return list_agent_tools()


@router.post("/run", response_model=AgentToolRunResponse)
async def run_tool(payload: AgentToolRunRequest, db: AsyncSession = Depends(get_db_session)):
    try:
        return await run_agent_tool(db, payload)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
