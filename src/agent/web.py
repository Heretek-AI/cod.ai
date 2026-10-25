"""
The agent over HTTP (`src/agent/web.py`), used by the web GUI's agent mode.

The server owns the session: the browser sends only the new prompt, and the
conversation lives in `.cod/sessions/` exactly as in the terminal. A turn is a
server-sent event stream. When a tool call needs approval the stream sends an
`approval` event and the turn waits until the browser posts the answer to
`/api/agent/sessions/{id}/approvals/{approval_id}`. Closing the stream stops
the turn.

Every route here acts on the user's files, so the web server requires its
per-process token on each request (see `src/web_server.py`).
"""
import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import secrets
from typing import Any, AsyncIterator, Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.engine import (
    Agent,
    AgentConfig,
    ApiError,
    Approval,
    BlockStart,
    CompactionNotice,
    FallbackNotice,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolOutput,
    TurnEnd,
)
from src.agent.models import DEFAULT_MODEL, MODELS
from src.agent.permissions import InvalidRuleError, PermissionPolicy
from src.agent.prompt import build_agent_prompt
from src.agent.session import Session, SessionError
from src.agent.tools import ToolError, Toolbox

MAX_PROMPT_CHARS = 1_000_000
# Tool output shown in the browser; the model still gets the full result.
MAX_OUTPUT_PREVIEW = 4_000
SESSION_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")


@dataclass
class AgentSettings:
    root: Path
    sandbox: Literal["auto", "on", "off"] = "auto"


@dataclass
class LiveSession:
    agent: Agent | None = None
    busy: bool = False
    # Events for the turn in progress; the approver adds `approval` events here too.
    queue: asyncio.Queue | None = None
    approvals: dict[str, asyncio.Future] = field(default_factory=dict)


class CreateSession(BaseModel, extra="forbid"):
    model: str = DEFAULT_MODEL
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    thinking_display: Literal["summarized", "omitted"] = "summarized"
    mode: Literal["default", "accept-edits"] = "default"


class TurnRequest(BaseModel, extra="forbid"):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


class ApprovalAnswer(BaseModel, extra="forbid"):
    answer: Literal["yes", "no", "always"]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_payload(event: Any) -> tuple[str, dict[str, Any]] | None:
    """Maps an engine event to an SSE event name and data."""
    if isinstance(event, BlockStart):
        return "block", {"kind": event.kind}
    if isinstance(event, TextDelta):
        return "delta", {"kind": "text", "text": event.text}
    if isinstance(event, ThinkingDelta):
        return "delta", {"kind": "thinking", "text": event.text}
    if isinstance(event, ToolCall):
        return "tool_call", {"id": event.id, "name": event.name, "summary": event.summary}
    if isinstance(event, ToolOutput):
        content = event.content
        if len(content) > MAX_OUTPUT_PREVIEW:
            content = content[:MAX_OUTPUT_PREVIEW] + f"\n… {len(event.content) - MAX_OUTPUT_PREVIEW} more characters"
        return "tool_output", {"id": event.id, "content": content, "is_error": event.is_error, "outcome": event.outcome}
    if isinstance(event, FallbackNotice):
        return "fallback", {"from": event.from_model, "to": event.to_model}
    if isinstance(event, CompactionNotice):
        return "compaction", {}
    if isinstance(event, TurnEnd):
        return "done", {
            "stop_reason": event.stop_reason, "usage": event.usage, "model": event.model,
            "refusal_category": event.refusal_category,
        }
    if isinstance(event, ApiError):
        return "error", {"status": event.status, "message": event.message}
    return None


def approval_details(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """What the approval card shows besides the summary."""
    if name == "edit_file":
        return {"old": str(tool_input.get("old_string", ""))[:2000], "new": str(tool_input.get("new_string", ""))[:2000]}
    if name == "write_file":
        content = str(tool_input.get("content", ""))
        return {"lines": len(content.splitlines()), "preview": content[:2000]}
    return {}


class AgentService:
    """Holds the sessions this server process has open."""

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.live: dict[str, LiveSession] = {}

    def _make(self, session: Session, config: AgentConfig, mode: str) -> LiveSession:
        root = self.settings.root
        try:
            policy = PermissionPolicy.from_settings(root, mode)  # type: ignore[arg-type]
            toolbox = Toolbox(root, sandbox=self.settings.sandbox, memory=session.memory_tool)
        except (InvalidRuleError, ToolError) as exc:
            raise HTTPException(500, str(exc))
        live = LiveSession()
        live.agent = Agent(self.client(), session, toolbox, policy, self._approver(live), config)
        self.live[session.id] = live
        return live

    def client(self) -> anthropic.AsyncAnthropic:
        from src import web_server

        return web_server.get_client()

    def create(self, body: CreateSession) -> LiveSession:
        if body.model not in MODELS:
            raise HTTPException(422, f"unsupported model {body.model!r}")
        session = Session.create(self.settings.root, body.model, build_agent_prompt(self.settings.root))
        config = AgentConfig(model=body.model, effort=body.effort, thinking_display=body.thinking_display)
        return self._make(session, config, body.mode)

    def get(self, session_id: str) -> LiveSession:
        if session_id in self.live:
            return self.live[session_id]
        if not SESSION_ID.match(session_id):
            raise HTTPException(404, "no such session")
        try:
            session = Session.find(self.settings.root, session_id)
        except SessionError:
            raise HTTPException(404, "no such session")
        # A session from before a restart: resumed with default settings.
        return self._make(session, AgentConfig(model=session.model), "default")

    def _approver(self, live: LiveSession):
        async def approve(name: str, summary: str, tool_input: dict[str, Any]) -> Approval:
            approval_id = secrets.token_hex(8)
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            live.approvals[approval_id] = future
            await live.queue.put(("approval", {
                "id": approval_id, "name": name, "summary": summary, "details": approval_details(name, tool_input),
            }))
            try:
                return await future
            finally:
                live.approvals.pop(approval_id, None)

        return approve

    async def run_turn(self, live: LiveSession, prompt: str) -> AsyncIterator[str]:
        live.queue = asyncio.Queue()

        async def produce() -> None:
            try:
                async for event in live.agent.send(prompt):
                    payload = event_payload(event)
                    if payload:
                        await live.queue.put(payload)
            except Exception as exc:
                await live.queue.put(("error", {"status": None, "message": f"{type(exc).__name__}: {exc}"}))
            finally:
                await live.queue.put(None)

        task = asyncio.create_task(produce())
        try:
            yield _sse("start", {"session_id": live.agent.session.id, "model": live.agent.config.model})
            while True:
                item = await live.queue.get()
                if item is None:
                    break
                yield _sse(*item)
        finally:
            # The browser closed the stream: stop the turn and any approval it waits on.
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            for future in live.approvals.values():
                future.cancel()
            live.busy = False


def build_router(get_service) -> APIRouter:
    router = APIRouter(prefix="/api/agent")

    @router.post("/sessions")
    def create_session(body: CreateSession, service: AgentService = Depends(get_service)) -> dict[str, Any]:
        live = service.create(body)
        return {"id": live.agent.session.id, "model": live.agent.config.model, "root": str(service.settings.root)}

    @router.post("/sessions/{session_id}/turns")
    def start_turn(session_id: str, body: TurnRequest, service: AgentService = Depends(get_service)) -> StreamingResponse:
        live = service.get(session_id)
        if live.busy:
            raise HTTPException(409, "this session is already running a turn")
        live.busy = True
        if body.effort:
            live.agent.config.effort = body.effort
        return StreamingResponse(
            service.run_turn(live, body.prompt),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/sessions/{session_id}/approvals/{approval_id}")
    def answer_approval(
        session_id: str, approval_id: str, body: ApprovalAnswer, service: AgentService = Depends(get_service)
    ) -> dict[str, Any]:
        live = service.live.get(session_id)
        future = live.approvals.get(approval_id) if live else None
        if future is None or future.done():
            raise HTTPException(404, "no pending approval with that id")
        future.get_loop().call_soon_threadsafe(_resolve, future, body.answer)
        return {"ok": True}

    return router


def _resolve(future: asyncio.Future, answer: str) -> None:
    if not future.done():
        future.set_result(answer)
