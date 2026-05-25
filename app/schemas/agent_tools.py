from pydantic import BaseModel, Field


class AgentToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    tags: list[str]


class AgentToolRunRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    input: dict = Field(default_factory=dict)


class AgentToolRunResponse(BaseModel):
    tool_name: str
    result: dict
