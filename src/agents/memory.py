"""
Versioned file-based memory store (`src/agents/memory.py`).

Each key is a Markdown file under the memory root with a version number kept in
`.versions.json`. Writes, appends and exact-match replacements take an optional
`if_version` guard so concurrent writers can't silently clobber each other.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import Any


class MemoryConcurrencyError(RuntimeError):
    """Raised when `if_version` does not match the current atomic version of a memory file."""


class MemoryKeyError(ValueError):
    """Raised when a key is absolute, contains `..`, or names the store's own version file."""


class MemoryMatchError(ValueError):
    """Raised when `old_str` in `memory_str_replace` matches 0 times or more than once (ambiguous)."""


@dataclass(frozen=True)
class MemoryFileState:
    key: str
    path: str
    version: int
    content: str


class StructuredMemoryStore:
    """
    Thread-safe, version-guarded file-based memory system for multi-agent coordination.
    """

    def __init__(self, memory_root: str | Path) -> None:
        self.memory_root = Path(memory_root).resolve()
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.memory_root / "_versions.json"
        self._lock = threading.Lock()
        self._versions: dict[str, int] = self._load_versions()

    def _load_versions(self) -> dict[str, int]:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_versions(self) -> None:
        self._meta_path.write_text(json.dumps(self._versions, indent=2, sort_keys=True), encoding="utf-8")

    def _resolve_key_path(self, key: str) -> Path:
        parts = Path(key).parts
        if not key or Path(key).is_absolute() or ".." in parts or key == self._meta_path.name:
            raise MemoryKeyError(f"invalid memory key {key!r}")
        target = (self.memory_root / key).resolve()
        if not target.is_relative_to(self.memory_root):
            raise MemoryKeyError(f"memory key {key!r} escapes the memory root")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def read_memory(self, key: str) -> MemoryFileState:
        with self._lock:
            target = self._resolve_key_path(key)
            if not target.exists():
                raise FileNotFoundError(f"Memory key '{key}' not found.")
            ver = self._versions.get(key, 1)
            return MemoryFileState(
                key=key,
                path=str(target),
                version=ver,
                content=target.read_text(encoding="utf-8"),
            )

    def memory_write(self, key: str, content: str, if_version: int | None = None) -> MemoryFileState:
        """
        Writes or overwrites a memory file atomically. If `if_version` is specified, verifies
        that the current version matches `if_version` before writing.
        """
        with self._lock:
            target = self._resolve_key_path(key)
            curr_ver = self._versions.get(key, 0)
            if if_version is not None and curr_ver != if_version:
                raise MemoryConcurrencyError(
                    f"Version conflict on '{key}': expected if_version={if_version}, but actual version is {curr_ver}."
                )
            new_ver = curr_ver + 1
            target.write_text(content, encoding="utf-8")
            self._versions[key] = new_ver
            self._save_versions()
            return MemoryFileState(key=key, path=str(target), version=new_ver, content=content)

    def memory_append(self, key: str, text_to_append: str, if_version: int | None = None) -> MemoryFileState:
        """Appends content to a memory file with optional `if_version` optimistic concurrency check."""
        with self._lock:
            target = self._resolve_key_path(key)
            curr_ver = self._versions.get(key, 0)
            if if_version is not None and curr_ver != if_version:
                raise MemoryConcurrencyError(
                    f"Version conflict on '{key}': expected if_version={if_version}, actual={curr_ver}."
                )
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            updated = existing + text_to_append
            new_ver = curr_ver + 1
            target.write_text(updated, encoding="utf-8")
            self._versions[key] = new_ver
            self._save_versions()
            return MemoryFileState(key=key, path=str(target), version=new_ver, content=updated)

    def memory_str_replace(
        self,
        key: str,
        old_str: str,
        new_str: str,
        if_version: int,
    ) -> MemoryFileState:
        """
        Atomic string replacement requiring:
          1. Exact `if_version` match against current file version.
          2. `old_str` is non-empty and occurs EXACTLY ONCE in the file.
        """
        if not old_str:
            raise MemoryMatchError("old_str cannot be empty in memory_str_replace.")

        with self._lock:
            target = self._resolve_key_path(key)
            if not target.exists():
                raise FileNotFoundError(f"Memory key '{key}' does not exist.")
            curr_ver = self._versions.get(key, 1)
            if curr_ver != if_version:
                raise MemoryConcurrencyError(
                    f"Concurrency Guard Triggered on '{key}': expected if_version={if_version}, actual={curr_ver}."
                )

            existing = target.read_text(encoding="utf-8")
            occurrences = existing.count(old_str)
            if occurrences == 0:
                raise MemoryMatchError(f"old_str not found in '{key}'.")
            if occurrences > 1:
                raise MemoryMatchError(
                    f"Ambiguous old_str in '{key}': found {occurrences} occurrences (must be unique == 1)."
                )

            updated = existing.replace(old_str, new_str, 1)
            new_ver = curr_ver + 1
            target.write_text(updated, encoding="utf-8")
            self._versions[key] = new_ver
            self._save_versions()
            return MemoryFileState(key=key, path=str(target), version=new_ver, content=updated)

    def todo_write(self, todos: list[dict[str, str]]) -> MemoryFileState:
        """
        Synchronizes structured Todo items (`id`, `content`, `status`) into `NOTES.md`
        (modeled on Claude Code's `TodoWrite` + live `NOTES.md` state tracker).
        """
        lines = ["# Live Session State Tracker (`NOTES.md` / `TodoWrite`)", ""]
        for item in todos:
            tid = item.get("id", "task")
            status = item.get("status", "pending")
            marker = "[x]" if status == "completed" else ("[/]" if status == "in_progress" else "[ ]")
            lines.append(f"- {marker} **{tid}** ({status}): {item.get('content', '')}")
        markdown = "\n".join(lines) + "\n"
        return self.memory_write("NOTES.md", markdown)
