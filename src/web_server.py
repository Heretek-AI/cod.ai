#!/usr/bin/env python3
"""
Local web chat server for cod.ai (`/src/web_server.py`).

Serves the single-page GUI in `web/index.html` and proxies chat turns to the
Claude Messages API as a server-sent event stream. Credentials never reach the
browser: the Anthropic client resolves them on the server (`ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile), and `ANTHROPIC_BASE_URL`
points it at a gateway such as the local credential proxy.

The browser owns the conversation history and sends it back each turn. The
server only ever appends to it, so prompt caching and preserved thinking keep
working: assistant turns are echoed back exactly as the API returned them.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import anthropic
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.agent.models import DEFAULT_MODEL, EFFORT_LEVELS, FALLBACK_BETA, MODELS, fallback_params, history_content
from src.agent.prompt import project_files_block

logger = logging.getLogger("cod.web")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
WEB_INDEX_PATH = WORKSPACE_ROOT / "web" / "index.html"

THINKING_DISPLAYS = ("summarized", "omitted")

MAX_OUTPUT_TOKENS = 64_000
MAX_MESSAGES = 1_000
MAX_REQUEST_CHARS = 8_000_000

NOT_SENT_MESSAGE = (
    "The request could not be sent. If no credentials are configured, set ANTHROPIC_API_KEY "
    "or run `ant auth login`, then restart the server. Details are in the server log."
)

BASE_SYSTEM_PROMPT = (
    "You are cod.ai, a coding and architecture assistant chatting with a developer "
    "through a local web interface. Answer in GitHub-flavored Markdown and put code "
    "in fenced blocks tagged with their language."
)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def build_system_prompt(root: Path = WORKSPACE_ROOT) -> str:
    """
    Builds the system prompt once at startup so it stays byte-identical for the
    whole process: the base prompt plus the repository's CLAUDE.md and AGENTS.md.
    Set `COD_PROJECT_CONTEXT=0` to leave the project files out.
    """
    parts = [BASE_SYSTEM_PROMPT]
    if _env_flag("COD_PROJECT_CONTEXT", True):
        parts.extend(project_files_block(root))
    return "\n\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]

    @field_validator("content")
    @classmethod
    def _not_empty(cls, value: str | list[dict[str, Any]]) -> str | list[dict[str, Any]]:
        if isinstance(value, str) and not value.strip():
            raise ValueError("message content is empty")
        if isinstance(value, list):
            if not value:
                raise ValueError("message content is empty")
            if any(not isinstance(block.get("type"), str) for block in value):
                raise ValueError("every content block needs a string 'type'")
        return value


class ChatRequest(BaseModel):
    model: str = DEFAULT_MODEL
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    thinking_display: Literal["summarized", "omitted"] = "summarized"
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        if value not in MODELS:
            raise ValueError(f"unsupported model {value!r}")
        return value

    @model_validator(mode="after")
    def _well_formed_history(self) -> "ChatRequest":
        if self.messages[0].role != "user":
            raise ValueError("the conversation must start with a user message")
        if self.messages[-1].role != "user":
            raise ValueError("the conversation must end with a user message")
        size = len(json.dumps([m.model_dump() for m in self.messages]))
        if size > MAX_REQUEST_CHARS:
            raise ValueError(f"conversation is too large ({size} characters)")
        return self


def build_request_params(req: ChatRequest, use_fallbacks: bool) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": req.model,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [m.model_dump() for m in req.messages],
        "thinking": {"type": "adaptive", "display": req.thinking_display},
        "output_config": {"effort": req.effort or MODELS[req.model]["default_effort"]},
        # Automatic caching: the breakpoint rolls forward to the newest block each
        # turn, so the system prompt and earlier history are read from cache.
        "cache_control": {"type": "ephemeral"},
    }
    params.update(fallback_params(req.model, use_fallbacks))
    return params


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat_events(client: anthropic.AsyncAnthropic, params: dict[str, Any]) -> AsyncIterator[str]:
    """
    Streams one turn as SSE events: `start`, `block` (a new content block),
    `delta` (thinking or text), then `done` with the final message, or `error`.
    """
    try:
        async with client.beta.messages.stream(**params) as stream:
            async for event in stream:
                if event.type == "message_start":
                    yield _sse("start", {"model": event.message.model})
                elif event.type == "content_block_start":
                    block = event.content_block.to_dict()
                    # Deltas carry the text; send the block's type and metadata only.
                    block.pop("text", None)
                    block.pop("thinking", None)
                    yield _sse("block", {"index": event.index, "block": block})
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield _sse("delta", {"index": event.index, "kind": "text", "text": event.delta.text})
                    elif event.delta.type == "thinking_delta":
                        yield _sse("delta", {"index": event.index, "kind": "thinking", "text": event.delta.thinking})
            final = await stream.get_final_message()

        content = [block.to_dict() for block in final.content]
        refused = final.stop_reason == "refusal"
        yield _sse("done", {
            "model": final.model,
            "stop_reason": final.stop_reason,
            "stop_details": final.stop_details.to_dict() if refused and final.stop_details else None,
            # A refused turn is discarded rather than echoed back.
            "history": None if refused else history_content(content),
            "usage": final.usage.to_dict(),
        })
    except anthropic.APIStatusError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        yield _sse("error", {"status": exc.status_code, "message": error.get("message") or exc.message})
    except anthropic.APIConnectionError:
        yield _sse("error", {"status": None, "message": "Could not reach the Claude API. Check the network or ANTHROPIC_BASE_URL."})
    except Exception:
        # Anything else fails before a request is sent, most often because no
        # credentials are configured (the SDK raises TypeError). Details stay in
        # the server log rather than going to the browser.
        logger.exception("chat request failed before reaching the API")
        yield _sse("error", {"status": None, "message": NOT_SENT_MESSAGE})


app = FastAPI(title="cod.ai web chat", version="0.2.0")


@app.get("/", response_class=HTMLResponse)
def serve_index() -> HTMLResponse:
    if WEB_INDEX_PATH.is_file():
        return HTMLResponse(WEB_INDEX_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>cod.ai web GUI not found</h1>", status_code=404)


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "default_model": DEFAULT_MODEL,
        "models": [{"id": model_id, **info} for model_id, info in MODELS.items()],
        "effort_levels": list(EFFORT_LEVELS),
        "thinking_displays": list(THINKING_DISPLAYS),
        "project_context": SYSTEM_PROMPT != BASE_SYSTEM_PROMPT,
    }


@app.post("/api/chat")
def chat(req: ChatRequest, client: anthropic.AsyncAnthropic = Depends(get_client)) -> StreamingResponse:
    params = build_request_params(req, use_fallbacks=_env_flag("COD_FALLBACKS", True))
    return StreamingResponse(
        stream_chat_events(client, params),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def run(host: str = "127.0.0.1", port: int = 8642) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
