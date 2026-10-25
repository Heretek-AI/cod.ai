"""
Client-side tools the agent can call (`src/agent/tools.py`).

Every path is resolved against the project root and rejected if it escapes it
(`..`, absolute paths elsewhere, symlinks out). Tool inputs come from the model,
so each one is validated against a pydantic model before anything runs, and
failures come back as `is_error` tool results rather than exceptions.
"""
from dataclasses import dataclass
import fnmatch
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

MAX_READ_LINES = 2000
MAX_OUTPUT_CHARS = 30_000
MAX_GLOB_RESULTS = 500
MAX_GREP_MATCHES = 300
DEFAULT_BASH_TIMEOUT = 120
MAX_BASH_TIMEOUT = 600

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cod", ".mypy_cache", ".pytest_cache"}

# Environment variables matching this pattern are removed before running shell
# commands, so the model can't read API keys or tokens through `env` or `echo`.
SECRET_ENV_PATTERN = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE)
# Kept despite matching: a socket path, not key material, and git over ssh needs it.
ENV_KEEP = frozenset({"SSH_AUTH_SOCK"})


class ToolError(Exception):
    """A failure reported back to the model as an `is_error` tool result."""


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class ReadFileInput(BaseModel, extra="forbid"):
    path: str
    offset: int = Field(default=1, ge=1)
    limit: int = Field(default=MAX_READ_LINES, ge=1, le=MAX_READ_LINES)


class WriteFileInput(BaseModel, extra="forbid"):
    path: str
    content: str


class EditFileInput(BaseModel, extra="forbid"):
    path: str
    old_string: str = Field(min_length=1)
    new_string: str
    replace_all: bool = False


class GlobInput(BaseModel, extra="forbid"):
    pattern: str = Field(min_length=1)


class GrepInput(BaseModel, extra="forbid"):
    pattern: str = Field(min_length=1)
    path: str = "."
    glob: str | None = None
    ignore_case: bool = False


class BashInput(BaseModel, extra="forbid"):
    command: str = Field(min_length=1)
    timeout: int = Field(default=DEFAULT_BASH_TIMEOUT, ge=1, le=MAX_BASH_TIMEOUT)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


# Tool definitions sent to the API, in a fixed order so the prompt prefix stays cacheable.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a text file in the project. Returns numbered lines. Use offset and limit for long files.",
        "input_schema": _schema({
            "path": {"type": "string", "description": "Path relative to the project root."},
            "offset": {"type": "integer", "description": "1-based line to start from."},
            "limit": {"type": "integer", "description": f"Number of lines to read (max {MAX_READ_LINES})."},
        }, ["path"]),
    },
    {
        "name": "write_file",
        "description": "Create a file or overwrite it completely. Prefer edit_file for changes to an existing file.",
        "input_schema": _schema({
            "path": {"type": "string", "description": "Path relative to the project root."},
            "content": {"type": "string", "description": "The full new contents of the file."},
        }, ["path", "content"]),
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file. old_string must match the file exactly, including "
            "whitespace, and must be unique unless replace_all is true. Read the file first."
        ),
        "input_schema": _schema({
            "path": {"type": "string", "description": "Path relative to the project root."},
            "old_string": {"type": "string", "description": "Exact text to replace."},
            "new_string": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of exactly one."},
        }, ["path", "old_string", "new_string"]),
    },
    {
        "name": "glob",
        "description": "Find files by glob pattern, e.g. 'src/**/*.py'. Returns paths relative to the project root.",
        "input_schema": _schema({
            "pattern": {"type": "string", "description": "Glob pattern relative to the project root."},
        }, ["pattern"]),
    },
    {
        "name": "grep",
        "description": "Search file contents with a regular expression. Returns path:line: text for each match.",
        "input_schema": _schema({
            "pattern": {"type": "string", "description": "Python regular expression."},
            "path": {"type": "string", "description": "File or directory to search, relative to the project root."},
            "glob": {"type": "string", "description": "Only search files whose name matches this glob, e.g. '*.py'."},
            "ignore_case": {"type": "boolean"},
        }, ["pattern"]),
    },
    {
        "name": "bash",
        "description": (
            "Run a shell command in the project root and return its exit code and output. Use it for "
            "tests, builds, git and other tools; use the file tools to read and edit files."
        ),
        "input_schema": _schema({
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": f"Seconds before the command is killed (max {MAX_BASH_TIMEOUT})."},
        }, ["command"]),
    },
]

TOOL_NAMES = tuple(t["name"] for t in TOOL_DEFINITIONS)
READ_ONLY_TOOLS = frozenset({"read_file", "glob", "grep"})


def api_tool_definitions(eager_input_streaming: bool = True) -> list[dict[str, Any]]:
    """Tool definitions for a streaming request; eager streaming sends large inputs as they are generated."""
    if not eager_input_streaming:
        return [dict(t) for t in TOOL_DEFINITIONS]
    return [{**t, "eager_input_streaming": True} for t in TOOL_DEFINITIONS]


def sanitized_env(base: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if base is None else base)
    return {k: v for k, v in source.items() if k in ENV_KEEP or not SECRET_ENV_PATTERN.search(k)}


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} characters]"


class Toolbox:
    """Runs tool calls against one project root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    # ---------- paths ----------

    def resolve(self, raw: str) -> Path:
        candidate = (self.root / raw).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ToolError(f"{raw} is outside the project root")
        return candidate

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() or "."

    def describe(self, name: str, tool_input: dict[str, Any]) -> str:
        """A one-line summary of a call, used for permission prompts and logs."""
        if name == "bash":
            return str(tool_input.get("command", ""))
        if name in ("glob", "grep"):
            return str(tool_input.get("pattern", ""))
        return str(tool_input.get("path", ""))

    # ---------- dispatch ----------

    def run(self, name: str, tool_input: Any) -> ToolResult:
        handlers: dict[str, tuple[type[BaseModel], Callable[[Any], str]]] = {
            "read_file": (ReadFileInput, self.read_file),
            "write_file": (WriteFileInput, self.write_file),
            "edit_file": (EditFileInput, self.edit_file),
            "glob": (GlobInput, self.glob),
            "grep": (GrepInput, self.grep),
            "bash": (BashInput, self.bash),
        }
        if name not in handlers:
            return ToolResult(f"Unknown tool {name!r}.", is_error=True)
        model, handler = handlers[name]
        try:
            args = model.model_validate(tool_input)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in exc.errors())
            return ToolResult(f"Invalid input for {name}: {problems}", is_error=True)
        try:
            return ToolResult(_truncate(handler(args)))
        except ToolError as exc:
            return ToolResult(str(exc), is_error=True)
        except OSError as exc:
            return ToolResult(f"{name} failed: {exc.strerror or exc}", is_error=True)

    # ---------- tools ----------

    def read_file(self, args: ReadFileInput) -> str:
        path = self.resolve(args.path)
        if not path.is_file():
            raise ToolError(f"{args.path} is not a file")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise ToolError(f"{args.path} is not a UTF-8 text file")
        if not lines:
            return f"{args.path} is empty."
        start = args.offset - 1
        chunk = lines[start:start + args.limit]
        if not chunk:
            raise ToolError(f"{args.path} has {len(lines)} lines; offset {args.offset} is past the end")
        width = len(str(start + len(chunk)))
        body = "\n".join(f"{start + i + 1:>{width}}\t{line}" for i, line in enumerate(chunk))
        remaining = len(lines) - (start + len(chunk))
        if remaining > 0:
            body += f"\n… {remaining} more lines; read again with offset={start + len(chunk) + 1}"
        return body

    def write_file(self, args: WriteFileInput) -> str:
        path = self.resolve(args.path)
        if path.is_dir():
            raise ToolError(f"{args.path} is a directory")
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8")
        verb = "Overwrote" if existed else "Created"
        return f"{verb} {self.relative(path)} ({len(args.content.splitlines())} lines)."

    def edit_file(self, args: EditFileInput) -> str:
        path = self.resolve(args.path)
        if not path.is_file():
            raise ToolError(f"{args.path} is not a file")
        text = path.read_text(encoding="utf-8")
        count = text.count(args.old_string)
        if count == 0:
            raise ToolError(f"old_string was not found in {args.path}. Read the file and copy the text exactly.")
        if count > 1 and not args.replace_all:
            raise ToolError(f"old_string appears {count} times in {args.path}. Add surrounding context or set replace_all.")
        if args.old_string == args.new_string:
            raise ToolError("old_string and new_string are identical")
        updated = text.replace(args.old_string, args.new_string) if args.replace_all else text.replace(args.old_string, args.new_string, 1)
        path.write_text(updated, encoding="utf-8")
        return f"Edited {self.relative(path)} ({count if args.replace_all else 1} replacement{'s' if args.replace_all and count > 1 else ''})."

    def _walk_files(self, base: Path):
        if base.is_file():
            yield base
            return
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                yield Path(dirpath) / filename

    def glob(self, args: GlobInput) -> str:
        if Path(args.pattern).is_absolute() or ".." in Path(args.pattern).parts:
            raise ToolError("glob patterns must stay inside the project root")
        matches = []
        for path in sorted(self.root.glob(args.pattern)):
            rel_parts = path.relative_to(self.root).parts
            if any(part in SKIP_DIRS for part in rel_parts) or not path.is_file():
                continue
            matches.append(self.relative(path))
            if len(matches) >= MAX_GLOB_RESULTS:
                break
        if not matches:
            return "No files matched."
        suffix = f"\n… stopped at {MAX_GLOB_RESULTS} results" if len(matches) >= MAX_GLOB_RESULTS else ""
        return "\n".join(matches) + suffix

    def grep(self, args: GrepInput) -> str:
        try:
            regex = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
        except re.error as exc:
            raise ToolError(f"invalid regular expression: {exc}")
        base = self.resolve(args.path)
        if not base.exists():
            raise ToolError(f"{args.path} does not exist")
        hits: list[str] = []
        for path in self._walk_files(base):
            if args.glob and not fnmatch.fnmatch(path.name, args.glob):
                continue
            try:
                with path.open(encoding="utf-8") as handle:
                    for number, line in enumerate(handle, 1):
                        if regex.search(line):
                            hits.append(f"{self.relative(path)}:{number}: {line.rstrip()[:300]}")
                            if len(hits) >= MAX_GREP_MATCHES:
                                return "\n".join(hits) + f"\n… stopped at {MAX_GREP_MATCHES} matches"
            except (UnicodeDecodeError, OSError):
                continue
        return "\n".join(hits) if hits else "No matches."

    def bash(self, args: BashInput) -> str:
        try:
            proc = subprocess.run(
                ["bash", "-c", args.command],
                cwd=self.root,
                env=sanitized_env(),
                capture_output=True,
                text=True,
                timeout=args.timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
            raise ToolError(f"Command timed out after {args.timeout}s.\n{_truncate(partial, 5000)}".rstrip())
        output = proc.stdout
        if proc.stderr:
            output += ("\n" if output else "") + proc.stderr
        return f"exit code {proc.returncode}\n{output}".rstrip()
