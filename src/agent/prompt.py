"""
System prompt for the agent (`src/agent/prompt.py`).

The prompt is built once when a session starts and stored in the session
header, so it is byte-identical on every request of that session, including
after a resume. Project files are read from the project root at that moment.
"""
from datetime import date
from pathlib import Path
import platform

PROJECT_FILES = ("CLAUDE.md", "AGENTS.md")

AGENT_PROMPT = """You are cod.ai, a coding agent working in the user's project through a terminal.

You can read, search and edit files in the project and run shell commands. Paths are relative to the project root. Read a file before you edit it, keep changes to what the task needs, and match the style of the surrounding code. Run the project's tests or build after a change when they exist, and report what they printed.

Some tool calls need the user's approval. If a call is denied, don't retry it unchanged: ask what the user would like instead, or find another way.

Shell commands run without secrets in their environment and without a terminal, so they can't prompt for input. Prefer non-interactive flags.

Answer in GitHub-flavored Markdown. When you finish, say briefly what you changed and anything left undone."""


def project_files_block(root: str | Path, names: tuple[str, ...] = PROJECT_FILES) -> list[str]:
    """Each project instruction file in `root`, wrapped in a `project_file` tag."""
    blocks = []
    for name in names:
        path = Path(root) / name
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            blocks.append(f'<project_file name="{name}">\n{text}\n</project_file>')
    return blocks


def build_agent_prompt(root: str | Path, include_project_files: bool = True, today: date | None = None) -> str:
    root = Path(root).resolve()
    environment = (
        "<environment>\n"
        f"Project root: {root}\n"
        f"Platform: {platform.system()} {platform.release()}\n"
        f"Session started: {(today or date.today()).isoformat()}\n"
        "</environment>"
    )
    parts = [AGENT_PROMPT, environment]
    if include_project_files:
        parts.extend(project_files_block(root))
    return "\n\n".join(parts)
