"""
The agent loop (`src/agent/engine.py`).

`Agent.send(prompt)` runs one user turn: it streams a request to the Messages
API, runs the tool calls in the response (asking the user first when the
permission policy says so), sends the results back, and repeats until Claude
ends its turn. Progress comes back as a stream of events for a front end to
render.

The history is append-only. Assistant content is stored exactly as the API
returned it, every message is written to the session file once it is final,
and the system prompt and tool list never change within a session, so each
request reads the earlier conversation from the prompt cache.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

import anthropic

from src.agent.models import (
    DEFAULT_COMPACT_AT,
    DEFAULT_MODEL,
    MODELS,
    compaction_params,
    fallback_params,
    history_content,
    merge_params,
)
from src.agent.permissions import EDIT_TOOLS, READ_ONLY_TOOLS, PermissionPolicy, Rule
from src.agent.prompt import build_explore_prompt
from src.agent.session import Session
from src.agent.tools import TOOL_NAMES, Toolbox, ToolResult, api_tool_definitions

MAX_OUTPUT_TOKENS = 64_000
MAX_TOOL_ROUNDS = 50
EXPLORE_TOOL_ROUNDS = 25
MAX_EXPLORE_TASK_CHARS = 20_000

DENIED_MESSAGE = "The user denied this tool call. Don't retry it unchanged; ask them how to proceed if you need it."
BLOCKED_MESSAGE = "This tool call is blocked by the project's permission settings."
TRUNCATED_MESSAGE = (
    "Your response hit the output limit before this tool call was complete, so it was not run. "
    "Retry with a smaller input, for example by writing the file in parts with edit_file."
)
INTERRUPTED_MESSAGE = "The user interrupted the turn before this tool call finished."

Approval = Literal["yes", "no", "always"]
# Asked when the policy says "ask": (tool name, one-line summary, full input) -> answer.
Approver = Callable[[str, str, dict[str, Any]], Awaitable[Approval]]


# ---------- events ----------

@dataclass
class TextDelta:
    text: str


@dataclass
class ThinkingDelta:
    text: str


@dataclass
class BlockStart:
    """A new text or thinking block starts; front ends use it to break lines."""
    kind: str


@dataclass
class ToolCall:
    id: str
    name: str
    summary: str
    input: dict[str, Any]


@dataclass
class ToolOutput:
    id: str
    name: str
    content: str
    is_error: bool
    outcome: Literal["ran", "denied", "blocked", "truncated"] = "ran"


@dataclass
class FallbackNotice:
    from_model: str | None
    to_model: str | None


@dataclass
class CompactionNotice:
    """The API summarized the earlier conversation to make room."""


@dataclass
class TurnEnd:
    """
    The turn is over. `stop_reason` is the API's on the last response, or
    `tool_rounds` when the loop hit `MAX_TOOL_ROUNDS`. On a refusal the turn's
    messages are rolled back and `refusal_category` says why, when known.
    """
    stop_reason: str | None
    usage: dict[str, int]
    model: str
    refusal_category: str | None = None


@dataclass
class ApiError:
    status: int | None
    message: str


Event = TextDelta | ThinkingDelta | BlockStart | ToolCall | ToolOutput | FallbackNotice | CompactionNotice | TurnEnd | ApiError


@dataclass
class _Final:
    message: Any


@dataclass
class AgentConfig:
    model: str = DEFAULT_MODEL
    effort: str | None = None
    thinking_display: Literal["summarized", "omitted"] = "summarized"
    fallbacks: bool = True
    max_tokens: int = MAX_OUTPUT_TOKENS
    max_tool_rounds: int = MAX_TOOL_ROUNDS
    # Input size that triggers server-side compaction; None turns it off.
    compact_at: int | None = DEFAULT_COMPACT_AT


@dataclass
class Usage:
    totals: dict[str, int] = field(default_factory=dict)

    def add(self, usage: Any) -> None:
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                self.totals[key] = self.totals.get(key, 0) + value


def api_error_message(exc: anthropic.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return error.get("message") or exc.message


class Agent:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        session: Session,
        toolbox: Toolbox,
        policy: PermissionPolicy,
        approver: Approver,
        config: AgentConfig | None = None,
        read_only: bool = False,
    ) -> None:
        self.client = client
        self.session = session
        self.toolbox = toolbox
        self.policy = policy
        self.approver = approver
        self.config = config or AgentConfig(model=session.model)
        if self.config.model not in MODELS:
            raise ValueError(f"unsupported model {self.config.model!r}")
        if session.memory_tool and toolbox.memory is None:
            raise ValueError("this session uses the memory tool, but the toolbox has no memory store")
        self.tools = api_tool_definitions(memory=session.memory_tool, explore=session.explore_tool)
        if read_only:
            self.tools = [t for t in self.tools if t["name"] in READ_ONLY_TOOLS]
        # The current turn's usage; explore sub-agents add theirs to it.
        self._turn_usage = Usage()
        # Results of the tool round in progress, kept so an interrupt can record them.
        self._pending_results: list[dict[str, Any]] | None = None

    def request_params(self) -> dict[str, Any]:
        cfg = self.config
        params: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "system": self.session.system_prompt,
            "tools": self.tools,
            "messages": list(self.session.messages),
            "thinking": {"type": "adaptive", "display": cfg.thinking_display},
            "output_config": {"effort": cfg.effort or MODELS[cfg.model]["default_effort"]},
            # Automatic caching: the breakpoint moves to the newest block each request.
            "cache_control": {"type": "ephemeral"},
        }
        return merge_params(params, fallback_params(cfg.model, cfg.fallbacks), compaction_params(cfg.compact_at))

    async def send(self, prompt: str) -> AsyncIterator[Event]:
        """Runs one user turn and yields its events, ending with `TurnEnd` or `ApiError`."""
        turn_start = len(self.session.messages)
        self.session.append({"role": "user", "content": prompt})
        usage = self._turn_usage = Usage()
        model = self.config.model
        rounds = 0
        try:
            while True:
                final = None
                async for event in self._stream(usage):
                    if isinstance(event, ApiError):
                        yield event
                        return
                    if isinstance(event, _Final):
                        final = event.message
                    else:
                        yield event
                if final is None:
                    yield ApiError(None, "The response ended without a message.")
                    return
                model = final.model

                if final.stop_reason == "refusal":
                    # The partial answer and the prompt that caused it are dropped,
                    # so the user can rephrase without the refusal in the history.
                    self.session.rollback(len(self.session.messages) - turn_start)
                    details = final.stop_details
                    category = getattr(details, "category", None) if details else None
                    yield TurnEnd("refusal", usage.totals, model, refusal_category=category)
                    return

                content = history_content([block.to_dict() for block in final.content])
                self.session.append({"role": "assistant", "content": content})

                if final.stop_reason == "pause_turn":
                    # The server paused a long turn; sending the history back resumes it.
                    continue

                tool_uses = [b for b in content if b.get("type") == "tool_use"]
                if not tool_uses:
                    yield TurnEnd(final.stop_reason, usage.totals, model)
                    return

                results = self._pending_results = []
                truncated = final.stop_reason == "max_tokens"
                for block in tool_uses:
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    yield ToolCall(block["id"], block["name"], self.toolbox.describe(block["name"], tool_input), tool_input)
                    output = await self._run_tool(block, truncated)
                    yield output
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": output.content,
                        "is_error": output.is_error,
                    })
                self._pending_results = None
                self.session.append({"role": "user", "content": results})

                rounds += 1
                if rounds >= self.config.max_tool_rounds:
                    yield TurnEnd("tool_rounds", usage.totals, model)
                    return
        except asyncio.CancelledError:
            self._close_open_tool_calls()
            raise

    async def _stream(self, usage: Usage) -> AsyncIterator[Any]:
        """Streams one request: yields deltas, then the final message or an `ApiError`."""
        try:
            async with self.client.beta.messages.stream(**self.request_params()) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        kind = event.content_block.type
                        if kind in ("text", "thinking"):
                            yield BlockStart(kind)
                        elif kind == "compaction":
                            yield CompactionNotice()
                        elif kind == "fallback":
                            block = event.content_block.to_dict()
                            yield FallbackNotice((block.get("from") or {}).get("model"), (block.get("to") or {}).get("model"))
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield TextDelta(event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            yield ThinkingDelta(event.delta.thinking)
                final = await stream.get_final_message()
        except anthropic.APIStatusError as exc:
            yield ApiError(exc.status_code, api_error_message(exc))
            return
        except anthropic.APIConnectionError:
            yield ApiError(None, "Could not reach the Claude API. Check the network or ANTHROPIC_BASE_URL.")
            return
        usage.add(final.usage)
        yield _Final(final)

    async def _run_tool(self, block: dict[str, Any], truncated: bool) -> ToolOutput:
        name = block["name"]
        tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
        if truncated:
            return ToolOutput(block["id"], name, TRUNCATED_MESSAGE, True, "truncated")
        summary = self.toolbox.describe(name, tool_input)
        decision = self.policy.decide(name, summary)
        if decision == "deny":
            return ToolOutput(block["id"], name, BLOCKED_MESSAGE, True, "blocked")
        if decision == "ask":
            answer = await self.approver(name, summary, tool_input)
            if answer == "no":
                return ToolOutput(block["id"], name, DENIED_MESSAGE, True, "denied")
            if answer == "always":
                # Edits are allowed tool-wide; shell commands only for this exact command.
                self.policy.allow_for_session(Rule(name) if name in EDIT_TOOLS else Rule(name, summary))
        if name == "explore" and self.session.explore_tool:
            result = await self._explore(tool_input)
        else:
            result = await asyncio.to_thread(self.toolbox.run, name, tool_input)
        return ToolOutput(block["id"], name, result.content, result.is_error)

    async def _explore(self, tool_input: dict[str, Any]) -> ToolResult:
        """Runs a read-only sub-agent on the task and returns its final report."""
        task = tool_input.get("task")
        if set(tool_input) != {"task"} or not isinstance(task, str) or not task.strip():
            return ToolResult("Invalid input for explore: expected {\"task\": \"<non-empty string>\"}.", is_error=True)
        if len(task) > MAX_EXPLORE_TASK_CHARS:
            return ToolResult(f"The explore task is too long ({len(task)} characters).", is_error=True)
        # Everything but the read-only tools is denied outright, whatever the model asks for.
        policy = PermissionPolicy(deny=[Rule(n) for n in TOOL_NAMES if n not in READ_ONLY_TOOLS])
        session = Session.ephemeral(self.config.model, build_explore_prompt(self.toolbox.root))
        config = AgentConfig(
            model=self.config.model, effort=self.config.effort, thinking_display="omitted",
            fallbacks=self.config.fallbacks, max_tool_rounds=EXPLORE_TOOL_ROUNDS, compact_at=self.config.compact_at,
        )
        sub = Agent(self.client, session, self.toolbox, policy, _deny, config, read_only=True)
        end: TurnEnd | ApiError | None = None
        async for event in sub.send(task):
            if isinstance(event, (TurnEnd, ApiError)):
                end = event
        if isinstance(end, TurnEnd):
            for key, value in end.usage.items():
                self._turn_usage.totals[key] = self._turn_usage.totals.get(key, 0) + value
        if isinstance(end, ApiError) or end is None:
            return ToolResult(f"The explorer failed: {end.message if end else 'no response'}", is_error=True)
        if end.stop_reason == "refusal":
            return ToolResult("The explorer declined this task.", is_error=True)
        report = _last_text(session.messages)
        if end.stop_reason == "tool_rounds":
            report = (report + "\n\n" if report else "") + "(The explorer stopped at its tool-round limit before finishing.)"
        return ToolResult(report or "The explorer finished without a report.", is_error=not report)

    def _close_open_tool_calls(self) -> None:
        """After an interrupt, answers any tool calls left without results so the history stays valid."""
        if not self.session.messages or self.session.messages[-1]["role"] != "assistant":
            return
        content = self.session.messages[-1]["content"]
        finished = list(self._pending_results or [])
        self._pending_results = None
        done = {r["tool_use_id"] for r in finished}
        pending = [b["id"] for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and b["id"] not in done]
        if finished or pending:
            self.session.append({"role": "user", "content": finished + [
                {"type": "tool_result", "tool_use_id": tool_id, "content": INTERRUPTED_MESSAGE, "is_error": True}
                for tool_id in pending
            ]})


async def _deny(name: str, summary: str, tool_input: dict[str, Any]) -> Approval:
    return "no"


def _last_text(messages: list[dict[str, Any]]) -> str:
    """The text of the last assistant message that has any."""
    for message in reversed(messages):
        if message["role"] == "assistant" and isinstance(message["content"], list):
            text = "".join(b.get("text", "") for b in message["content"] if b.get("type") == "text").strip()
            if text:
                return text
    return ""
