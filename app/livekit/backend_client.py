import httpx


class BackendClient:
    def __init__(self, api_base_url: str) -> None:
        self.api_base_url = api_base_url.rstrip("/")

    async def submit_voice_transcript(self, *, voice_session_id: str, transcript: str, language: str | None = None) -> dict:
        payload = {"voice_session_id": voice_session_id, "transcript": transcript}
        if language:
            payload["language"] = language
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_base_url}/voice/events", json=payload)
            response.raise_for_status()
            return response.json()

    async def run_agent_tool(self, *, tool_name: str, input_payload: dict) -> dict:
        payload = {"tool_name": tool_name, "input": input_payload}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_base_url}/agent-tools/run", json=payload)
            response.raise_for_status()
            return response.json()["result"]


def format_qa_result(result: dict) -> str:
    label = result.get("violation_label", "unknown")
    score = result.get("final_score", "unknown")
    escalation = "required" if result.get("escalation_required") else "not required"
    coaching = result.get("coaching_note", "No coaching note returned.")
    return f"QA score {score}. Label {label}. Escalation {escalation}. {coaching}"
