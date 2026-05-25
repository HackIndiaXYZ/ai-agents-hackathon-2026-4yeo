from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings
from app.livekit.backend_client import BackendClient, format_qa_result


def run() -> None:
    try:
        from livekit import agents
        from livekit.agents import Agent, AgentServer, AgentSession, inference, room_io
    except ImportError as exc:
        raise RuntimeError("LiveKit Agents dependencies are not installed. Run `pip install -r requirements.txt`.") from exc

    settings = get_settings()
    server = AgentServer()

    class ArgusAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=settings.worker.instructions)

        async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
            voice_session_id = _metadata_value(self, "voice_session_id")
            language = _metadata_value(self, "language")
            transcript = _message_text(new_message)
            if not voice_session_id or not transcript:
                return
            result = await BackendClient(settings.worker.api_base_url).submit_voice_transcript(
                voice_session_id=voice_session_id,
                transcript=transcript,
                language=language,
            )
            await self.session.say(format_qa_result(result))

    @server.rtc_session(agent_name=settings.livekit.agent_name)
    async def argus_awaaz_agent(ctx: agents.JobContext):
        session = AgentSession(
            stt=inference.STT(model=settings.worker.stt_model, language="multi"),
            llm=inference.LLM(model=settings.worker.llm_model),
            tts=inference.TTS(model=settings.worker.tts_model, voice=settings.worker.tts_voice),
        )
        await session.start(
            agent=ArgusAgent(),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                text_input=True,
                audio_input=True,
                text_output=True,
                audio_output=True,
            ),
        )

    agents.cli.run_app(server)


def _metadata_value(agent: Any, key: str) -> str | None:
    participant = getattr(getattr(getattr(agent, "session", None), "room_io", None), "linked_participant", None)
    metadata = getattr(participant, "metadata", None)
    if not metadata:
        return None
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        return None
    value = payload.get(key)
    return str(value) if value is not None else None


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [part for part in content if isinstance(part, str)]
        return " ".join(parts).strip()
    return str(content).strip()


if __name__ == "__main__":
    run()
