"""
Append-only session files (`src/agent/session.py`).

A session is a JSONL file under `<project>/.cod/sessions/`. The first line is a
header with the model and the frozen system prompt; every later line is one
message, written as soon as it is final. A `rollback` line drops the last few
messages (used when a turn is refused), so the file itself is never rewritten.
Resuming replays the messages exactly as they were sent, so the prompt cache
and thinking blocks stay valid.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any

SESSIONS_DIR = Path(".cod") / "sessions"
SESSION_ID_PATTERN = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}")


class SessionError(RuntimeError):
    pass


@dataclass
class Session:
    path: Path | None
    id: str
    model: str
    system_prompt: str
    created_at: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    # Whether the session's tool list includes the memory tool. Fixed at creation
    # so the tool list, like the system prompt, is the same on every request.
    memory_tool: bool = True
    explore_tool: bool = False

    @classmethod
    def create(
        cls, root: str | Path, model: str, system_prompt: str, memory_tool: bool = True, explore_tool: bool = True
    ) -> "Session":
        directory = Path(root) / SESSIONS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        created = datetime.now(timezone.utc)
        session_id = created.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        session = cls(
            directory / f"{session_id}.jsonl", session_id, model, system_prompt, created.isoformat(),
            memory_tool=memory_tool, explore_tool=explore_tool,
        )
        header = {
            "type": "session", "id": session_id, "model": model, "system_prompt": system_prompt,
            "created_at": session.created_at, "memory_tool": memory_tool, "explore_tool": explore_tool,
        }
        session.path.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")
        return session

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        path = Path(path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise SessionError(f"no session file at {path}") from exc
        records = []
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SessionError(f"{path}:{number} is not valid JSON") from exc
        if not records or records[0].get("type") != "session":
            raise SessionError(f"{path} has no session header")
        header = records[0]
        messages: list[dict[str, Any]] = []
        for record in records[1:]:
            if record.get("type") == "message":
                messages.append(record["message"])
            elif record.get("type") == "rollback":
                del messages[len(messages) - int(record["count"]):]
        return cls(
            path, header["id"], header["model"], header["system_prompt"], header["created_at"], messages,
            memory_tool=bool(header.get("memory_tool", False)),
            explore_tool=bool(header.get("explore_tool", False)),
        )

    @classmethod
    def find(cls, root: str | Path, session_id: str | None = None) -> "Session":
        """Loads a session by id, or the most recent one when no id is given."""
        directory = Path(root) / SESSIONS_DIR
        if session_id:
            # Ids come from the command line or a URL, so only the generated form is accepted.
            if not SESSION_ID_PATTERN.fullmatch(session_id):
                raise SessionError(f"invalid session id {session_id!r}")
            base = os.path.realpath(directory)
            path = os.path.realpath(os.path.join(base, f"{session_id}.jsonl"))
            if not path.startswith(base + os.sep):
                raise SessionError(f"invalid session id {session_id!r}")
            return cls.load(path)
        candidates = sorted(directory.glob("*.jsonl")) if directory.is_dir() else []
        if not candidates:
            raise SessionError(f"no sessions in {directory}")
        return cls.load(candidates[-1])

    @classmethod
    def ephemeral(cls, model: str, system_prompt: str) -> "Session":
        """A session kept in memory only, for sub-agents."""
        return cls(None, "ephemeral", model, system_prompt, datetime.now(timezone.utc).isoformat(), memory_tool=False)

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if self.path is None:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "message", "message": message}, ensure_ascii=False) + "\n")

    def rollback(self, count: int) -> None:
        """Drops the last `count` messages."""
        if count <= 0:
            return
        if count > len(self.messages):
            raise SessionError(f"cannot roll back {count} messages; the session has {len(self.messages)}")
        del self.messages[len(self.messages) - count:]
        if self.path is None:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "rollback", "count": count}) + "\n")
