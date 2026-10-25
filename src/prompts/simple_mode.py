"""
`COD_SIMPLE=true` Override (Modeled on Claude Code's `02_simple_mode.md`).
Strips all orchestration, sub-agent, and skills overhead down to a strict 4-line minimal prompt
(Identity, CWD, Date, Direct Execution Mandate) for raw model benchmarking.
"""
import os
from datetime import datetime, timezone


def build_simple_mode_prompt(cwd: str | None = None, fixed_date: str | None = None) -> str:
    """
    Returns an exact 4-line minimal system prompt when COD_SIMPLE=true is active.
    If fixed_date is omitted, uses YYYY-MM-DD (static per day to preserve intra-day prefix cache).
    """
    working_dir = cwd or os.getcwd()
    date_str = fixed_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "Identity: You are cod.ai running in COD_SIMPLE minimal benchmark mode.",
        f"CWD: {working_dir}",
        f"Date: {date_str}",
        "Directive: Answer directly and execute requested code changes using only core file primitives without orchestration overhead.",
    ]
    assert len(lines) == 4, "COD_SIMPLE prompt must be strictly 4 lines"
    return "\n".join(lines)


def is_simple_mode_enabled(env: dict[str, str] | None = None) -> bool:
    """Checks whether COD_SIMPLE=true is set in the environment dictionary or os.environ."""
    source = env if env is not None else os.environ
    val = source.get("COD_SIMPLE", "").strip().lower()
    return val in ("true", "1", "yes")
