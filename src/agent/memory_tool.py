"""
The memory tool (`src/agent/memory_tool.py`).

Implements the client side of Anthropic's `memory_20250818` tool: Claude sees
a `/memories` directory and keeps notes there across sessions. Here that
directory is `<project>/.cod/memory/`, so memories belong to the project.
Every path is checked to stay inside it, symlinks included.
"""
from pathlib import Path
import shutil
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

MEMORY_TOOL = {"type": "memory_20250818", "name": "memory"}
VIRTUAL_ROOT = "/memories"
MEMORY_DIR = Path(".cod") / "memory"
MAX_VIEW_ENTRIES = 200


class MemoryToolError(Exception):
    pass


class View(BaseModel, extra="forbid"):
    command: Literal["view"]
    path: str
    view_range: list[int] | None = Field(default=None, min_length=2, max_length=2)


class Create(BaseModel, extra="forbid"):
    command: Literal["create"]
    path: str
    file_text: str


class StrReplace(BaseModel, extra="forbid"):
    command: Literal["str_replace"]
    path: str
    old_str: str = Field(min_length=1)
    new_str: str


class Insert(BaseModel, extra="forbid"):
    command: Literal["insert"]
    path: str
    insert_line: int = Field(ge=0)
    insert_text: str


class Delete(BaseModel, extra="forbid"):
    command: Literal["delete"]
    path: str


class Rename(BaseModel, extra="forbid"):
    command: Literal["rename"]
    old_path: str
    new_path: str


Command = TypeAdapter(Annotated[Union[View, Create, StrReplace, Insert, Delete, Rename], Field(discriminator="command")])


def describe(tool_input: dict[str, Any]) -> str:
    """A one-line summary for permission rules: the command and its path."""
    path = tool_input.get("path") or tool_input.get("old_path") or ""
    return f"{tool_input.get('command', '')} {path}".strip()


class MemoryStore:
    def __init__(self, project_root: str | Path) -> None:
        self.root = (Path(project_root) / MEMORY_DIR).resolve()

    def _resolve(self, path: str) -> Path:
        if path != VIRTUAL_ROOT and not path.startswith(VIRTUAL_ROOT + "/"):
            raise MemoryToolError(f"Memory paths must start with {VIRTUAL_ROOT}, got {path!r}")
        relative = path[len(VIRTUAL_ROOT):].lstrip("/")
        target = (self.root / relative).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise MemoryToolError(f"{path} is outside {VIRTUAL_ROOT}")
        return target

    def _virtual(self, target: Path) -> str:
        relative = target.relative_to(self.root).as_posix()
        return VIRTUAL_ROOT if relative == "." else f"{VIRTUAL_ROOT}/{relative}"

    def run(self, tool_input: Any) -> str:
        try:
            command = Command.validate_python(tool_input)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in exc.errors())
            raise MemoryToolError(f"Invalid memory command: {problems}")
        self.root.mkdir(parents=True, exist_ok=True)
        return getattr(self, command.command)(command)

    def view(self, cmd: View) -> str:
        target = self._resolve(cmd.path)
        if target.is_dir():
            entries = []
            for path in sorted(target.rglob("*")):
                if any(part.startswith(".") for part in path.relative_to(target).parts):
                    continue
                suffix = "/" if path.is_dir() else f"  ({path.stat().st_size} bytes)"
                entries.append(self._virtual(path) + suffix)
                if len(entries) >= MAX_VIEW_ENTRIES:
                    entries.append("…")
                    break
            listing = "\n".join(entries) if entries else "(empty)"
            return f"Directory {self._virtual(target)}:\n{listing}"
        if not target.is_file():
            raise MemoryToolError(f"{cmd.path} does not exist")
        lines = target.read_text(encoding="utf-8").splitlines()
        start, end = 1, len(lines)
        if cmd.view_range:
            start, end = cmd.view_range[0], (len(lines) if cmd.view_range[1] == -1 else cmd.view_range[1])
            if start < 1 or end < start:
                raise MemoryToolError(f"invalid view_range {cmd.view_range}")
        return "\n".join(f"{n:>6}\t{lines[n - 1]}" for n in range(start, min(end, len(lines)) + 1))

    def create(self, cmd: Create) -> str:
        target = self._resolve(cmd.path)
        if target == self.root or target.is_dir():
            raise MemoryToolError(f"{cmd.path} is a directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cmd.file_text, encoding="utf-8")
        return f"Saved {cmd.path}."

    def _file(self, path: str) -> Path:
        target = self._resolve(path)
        if not target.is_file():
            raise MemoryToolError(f"{path} does not exist")
        return target

    def str_replace(self, cmd: StrReplace) -> str:
        target = self._file(cmd.path)
        text = target.read_text(encoding="utf-8")
        count = text.count(cmd.old_str)
        if count != 1:
            raise MemoryToolError(f"old_str appears {count} times in {cmd.path}; it must appear exactly once")
        target.write_text(text.replace(cmd.old_str, cmd.new_str, 1), encoding="utf-8")
        return f"Edited {cmd.path}."

    def insert(self, cmd: Insert) -> str:
        target = self._file(cmd.path)
        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        if cmd.insert_line > len(lines):
            raise MemoryToolError(f"insert_line {cmd.insert_line} is past the end of {cmd.path} ({len(lines)} lines)")
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        text = cmd.insert_text if cmd.insert_text.endswith("\n") else cmd.insert_text + "\n"
        lines.insert(cmd.insert_line, text)
        target.write_text("".join(lines), encoding="utf-8")
        return f"Inserted text at line {cmd.insert_line} of {cmd.path}."

    def delete(self, cmd: Delete) -> str:
        target = self._resolve(cmd.path)
        if target == self.root:
            raise MemoryToolError(f"Cannot delete {VIRTUAL_ROOT} itself")
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        else:
            raise MemoryToolError(f"{cmd.path} does not exist")
        return f"Deleted {cmd.path}."

    def rename(self, cmd: Rename) -> str:
        source = self._resolve(cmd.old_path)
        dest = self._resolve(cmd.new_path)
        if source == self.root or not source.exists():
            raise MemoryToolError(f"{cmd.old_path} does not exist")
        if dest.exists():
            raise MemoryToolError(f"{cmd.new_path} already exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
        return f"Renamed {cmd.old_path} to {cmd.new_path}."
