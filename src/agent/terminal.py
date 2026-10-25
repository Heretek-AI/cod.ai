"""
Terminal front end for the agent (`src/agent/terminal.py`).

`run_print` answers one prompt and exits (`cod -p`); `run_repl` is the
interactive loop (`cod`). Both render the same agent events. In print mode the
answer goes to stdout and everything else (thinking, tool calls) to stderr,
so the output can be piped.
"""
import asyncio
from dataclasses import dataclass
import sys
from typing import Any, Callable, TextIO

from src.agent.engine import (
    Agent,
    ApiError,
    Approval,
    BlockStart,
    CompactionNotice,
    Event,
    FallbackNotice,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolOutput,
    TurnEnd,
)

TOOL_PREVIEW_LINES = 8

HELP = """Commands:
  /help      show this help
  /session   show the session id and file
  /usage     show token usage for this session
  /exit      quit (Ctrl-D also works)
Ctrl-C stops the current turn."""


@dataclass
class Style:
    enabled: bool

    def wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def dim(self, text: str) -> str:
        return self.wrap("2", text)

    def bold(self, text: str) -> str:
        return self.wrap("1", text)

    def red(self, text: str) -> str:
        return self.wrap("31", text)


class Renderer:
    """Writes agent events to the terminal. `out` gets the answer text, `info` everything else."""

    def __init__(self, out: TextIO, info: TextIO, style: Style, show_thinking: bool = True) -> None:
        self.out = out
        self.info = info
        self.style = style
        self.show_thinking = show_thinking
        self._at_line_start = {id(out): True, id(info): True}
        self._block: str | None = None
        self.answer_parts: list[str] = []

    def write(self, stream: TextIO, text: str) -> None:
        if not text:
            return
        stream.write(text)
        stream.flush()
        self._at_line_start[id(stream)] = text.endswith("\n")

    def line(self, stream: TextIO, text: str) -> None:
        if not self._at_line_start.get(id(stream), True):
            self.write(stream, "\n")
        self.write(stream, text + "\n")

    def finish_block(self) -> None:
        for stream in (self.out, self.info):
            if not self._at_line_start.get(id(stream), True):
                self.write(stream, "\n")
        self._block = None

    def render(self, event: Event) -> None:
        if isinstance(event, BlockStart):
            self.finish_block()
            self._block = event.kind
            if event.kind == "thinking" and self.show_thinking:
                self.line(self.info, self.style.dim("thinking…"))
        elif isinstance(event, ThinkingDelta):
            if self.show_thinking:
                self.write(self.info, self.style.dim(event.text))
        elif isinstance(event, TextDelta):
            self.answer_parts.append(event.text)
            self.write(self.out, event.text)
        elif isinstance(event, FallbackNotice):
            self.finish_block()
            self.line(self.info, self.style.dim(f"(continuing on {event.to_model or 'a fallback model'})"))
        elif isinstance(event, CompactionNotice):
            self.finish_block()
            self.line(self.info, self.style.dim("(earlier conversation summarized to free up context)"))
        elif isinstance(event, ToolCall):
            self.finish_block()
            self.line(self.info, self.style.bold(f"● {event.name}") + f" {one_line(event.summary)}")
        elif isinstance(event, ToolOutput):
            self.render_tool_output(event)
        elif isinstance(event, TurnEnd):
            self.finish_block()
            note = turn_end_note(event)
            if note:
                self.line(self.info, self.style.red(note) if event.stop_reason == "refusal" else self.style.dim(note))
        elif isinstance(event, ApiError):
            self.finish_block()
            status = f" ({event.status})" if event.status else ""
            self.line(self.info, self.style.red(f"API error{status}: {event.message}"))

    def render_tool_output(self, event: ToolOutput) -> None:
        lines = event.content.splitlines() or [""]
        shown = lines[:TOOL_PREVIEW_LINES]
        if len(lines) > TOOL_PREVIEW_LINES:
            shown.append(f"… {len(lines) - TOOL_PREVIEW_LINES} more lines")
        text = "\n".join("  ⎿ " + line if i == 0 else "    " + line for i, line in enumerate(shown))
        self.line(self.info, self.style.red(text) if event.is_error else self.style.dim(text))


def one_line(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def turn_end_note(event: TurnEnd) -> str | None:
    if event.stop_reason == "refusal":
        category = f" ({event.refusal_category})" if event.refusal_category else ""
        return f"Claude declined this request{category}. It was left out of the conversation; try rephrasing."
    if event.stop_reason == "max_tokens":
        return "The response hit the output limit and was cut off. Ask Claude to continue."
    if event.stop_reason == "tool_rounds":
        return "Stopped after the maximum number of tool rounds in one turn. Send a message to continue."
    return None


def format_usage(usage: dict[str, int]) -> str:
    keys = (
        ("input_tokens", "in"),
        ("cache_read_input_tokens", "cache read"),
        ("cache_creation_input_tokens", "cache write"),
        ("output_tokens", "out"),
    )
    return " · ".join(f"{label} {usage.get(key, 0):,}" for key, label in keys)


def make_terminal_approver(
    read_line: Callable[[str], str],
    info: TextIO,
    style: Style,
) -> Callable[[str, str, dict[str, Any]], Any]:
    """Asks on the terminal. EOF or Ctrl-C at the prompt counts as a no."""

    async def approve(name: str, summary: str, tool_input: dict[str, Any]) -> Approval:
        info.write(style.bold(f"  Allow {name}?") + (f" {summary}\n" if name == "bash" and "\n" in summary else "\n"))
        if name == "write_file":
            preview = str(tool_input.get("content", "")).splitlines()
            info.write(style.dim(f"  ({len(preview)} lines)\n"))
        elif name == "edit_file":
            info.write(style.dim(f"  - {one_line(str(tool_input.get('old_string', '')), 200)}\n"))
            info.write(style.dim(f"  + {one_line(str(tool_input.get('new_string', '')), 200)}\n"))
        info.flush()
        while True:
            try:
                answer = read_line("  [y]es / [n]o / [a]lways for this session: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                info.write("\n")
                return "no"
            if answer in ("y", "yes"):
                return "yes"
            if answer in ("n", "no", ""):
                return "no"
            if answer in ("a", "always"):
                return "always"

    return approve


def make_deny_approver(info: TextIO, style: Style) -> Callable[[str, str, dict[str, Any]], Any]:
    """Used when there is no terminal to ask on: anything that needs approval is denied."""

    async def deny(name: str, summary: str, tool_input: dict[str, Any]) -> Approval:
        info.write(style.dim(
            f"  {name} needs approval and there is no terminal to ask on, so it was denied. "
            "Use --accept-edits, --allow-all or an allow rule in .cod/settings.json.\n"
        ))
        info.flush()
        return "no"

    return deny


async def run_turn(agent: Agent, prompt: str, renderer: Renderer) -> TurnEnd | ApiError | None:
    last = None
    try:
        async for event in agent.send(prompt):
            renderer.render(event)
            if isinstance(event, (TurnEnd, ApiError)):
                last = event
    except Exception as exc:
        # Failures before a request is sent, most often missing credentials.
        last = ApiError(None, f"{type(exc).__name__}: {exc}")
        renderer.render(last)
    return last


def run_print(agent: Agent, prompt: str, renderer: Renderer) -> int:
    """One prompt, then exit. Returns the process exit code."""
    try:
        last = asyncio.run(run_turn(agent, prompt, renderer))
    except KeyboardInterrupt:
        renderer.finish_block()
        return 130
    if isinstance(last, ApiError) or last is None:
        return 1
    return 2 if last.stop_reason == "refusal" else 0


def run_repl(agent: Agent, renderer: Renderer, read_line: Callable[[str], str] = input) -> int:
    style = renderer.style
    session = agent.session
    renderer.line(renderer.info, style.dim(f"cod.ai · {agent.config.model} · session {session.id} · /help for commands"))
    totals: dict[str, int] = {}
    with asyncio.Runner() as runner:
        while True:
            try:
                prompt = read_line(style.bold("> ")).strip()
            except EOFError:
                renderer.write(renderer.info, "\n")
                return 0
            except KeyboardInterrupt:
                renderer.write(renderer.info, "\n")
                continue
            if not prompt:
                continue
            if prompt in ("/exit", "/quit"):
                return 0
            if prompt == "/help":
                renderer.line(renderer.info, HELP)
                continue
            if prompt == "/session":
                renderer.line(renderer.info, f"{session.id}  {session.path}")
                continue
            if prompt == "/usage":
                renderer.line(renderer.info, format_usage(totals))
                continue
            try:
                last = runner.run(run_turn(agent, prompt, renderer))
            except KeyboardInterrupt:
                renderer.finish_block()
                renderer.line(renderer.info, style.dim("(interrupted)"))
                continue
            if isinstance(last, TurnEnd):
                for key, value in last.usage.items():
                    totals[key] = totals.get(key, 0) + value
                renderer.line(renderer.info, style.dim(format_usage(last.usage)))


def is_interactive(stream: TextIO = sys.stdin) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False
