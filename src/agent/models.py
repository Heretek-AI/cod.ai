"""
Model settings shared by the agent and the web server (`src/agent/models.py`).
"""
from typing import Any

# `fallbacks` marks models that accept the server-side `fallbacks: "default"`
# refusal fallback (Claude Haiku 5.5 has none).
MODELS: dict[str, dict[str, Any]] = {
    "claude-opus-5-5": {"label": "Claude Opus 5.5", "default_effort": "medium", "fallbacks": True},
    "claude-fable-5-1": {"label": "Claude Fable 5.1", "default_effort": "high", "fallbacks": True},
    "claude-sonnet-5-5": {"label": "Claude Sonnet 5.5", "default_effort": "high", "fallbacks": True},
    "claude-haiku-5-5": {"label": "Claude Haiku 5.5", "default_effort": "medium", "fallbacks": False},
}
DEFAULT_MODEL = "claude-opus-5-5"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
COMPACT_BETA = "compact-2026-01-12"
DEFAULT_COMPACT_AT = 150_000


def fallback_params(model: str, enabled: bool) -> dict[str, Any]:
    """Request fields that turn on the server-side refusal fallback where the model supports it."""
    if enabled and MODELS[model]["fallbacks"]:
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    return {}


def history_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Returns the assistant content to echo back on the next turn. After a
    mid-output fallback, only text (and any compaction summary) survives from
    the blocks before the last `fallback` marker; the marker and everything
    after it are kept unchanged so thinking blocks stay valid.
    """
    last_fallback = max((i for i, b in enumerate(content) if b.get("type") == "fallback"), default=-1)
    return [b for i, b in enumerate(content) if i >= last_fallback or b.get("type") in ("text", "compaction")]

def compaction_params(trigger_tokens: int | None) -> dict[str, Any]:
    """
    Server-side compaction: once the input passes `trigger_tokens`, the API
    summarizes the earlier conversation into a `compaction` block at the start
    of the response, and later requests read from that block onward.
    """
    if not trigger_tokens:
        return {}
    edit = {"type": "compact_20260112", "trigger": {"type": "input_tokens", "value": trigger_tokens}}
    return {"betas": [COMPACT_BETA], "context_management": {"edits": [edit]}}


def merge_params(*parts: dict[str, Any]) -> dict[str, Any]:
    """Merges request fragments, concatenating their `betas` lists."""
    merged: dict[str, Any] = {}
    for part in parts:
        for key, value in part.items():
            if key == "betas":
                merged["betas"] = merged.get("betas", []) + [b for b in value if b not in merged.get("betas", [])]
            else:
                merged[key] = value
    return merged
