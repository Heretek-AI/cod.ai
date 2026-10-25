"""
Permission rules for tool calls (`src/agent/permissions.py`).

A rule is `tool` or `tool(pattern)`, where the pattern is a shell-style glob
matched against the call's summary: the command for `bash`, the path for the
file tools, the pattern for `glob` and `grep`. Rules come in three lists:
`deny` always wins, then `allow`, then `ask`; anything unmatched falls back to
the mode's default (reads and the memory tool are allowed, edits and shell
commands ask). The memory tool's summary is its command and path, such as
`create /memories/notes.md`.

Rules are read from `.cod/settings.json` in the project:

    {"permissions": {"allow": ["bash(git status*)", "bash(pytest*)"],
                     "deny": ["bash(rm -rf*)", "read_file(.env*)"]}}
"""
from dataclasses import dataclass, field
import fnmatch
import json
from pathlib import Path
import re
from typing import Literal

from src.agent.tools import READ_ONLY_TOOLS, TOOL_NAMES

Decision = Literal["allow", "ask", "deny"]
Mode = Literal["default", "accept-edits", "allow-all"]

EDIT_TOOLS = frozenset({"write_file", "edit_file"})
# The memory tool only touches `.cod/memory/`, so it runs without asking.
AUTO_ALLOWED = READ_ONLY_TOOLS | {"memory"}
RULE_PATTERN = re.compile(r"^(?P<tool>[a-z_]+)(?:\((?P<pattern>.*)\))?$")


class InvalidRuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    tool: str
    pattern: str | None = None

    @classmethod
    def parse(cls, text: str) -> "Rule":
        match = RULE_PATTERN.match(text.strip())
        if not match or match["tool"] not in TOOL_NAMES:
            raise InvalidRuleError(f"invalid permission rule {text!r}; expected one of {', '.join(TOOL_NAMES)}, optionally with (pattern)")
        return cls(match["tool"], match["pattern"])

    def matches(self, tool: str, summary: str) -> bool:
        if tool != self.tool:
            return False
        return self.pattern is None or fnmatch.fnmatchcase(summary, self.pattern)

    def __str__(self) -> str:
        return self.tool if self.pattern is None else f"{self.tool}({self.pattern})"


@dataclass
class PermissionPolicy:
    mode: Mode = "default"
    allow: list[Rule] = field(default_factory=list)
    ask: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)

    @classmethod
    def from_settings(cls, root: str | Path, mode: Mode = "default") -> "PermissionPolicy":
        path = Path(root) / ".cod" / "settings.json"
        policy = cls(mode=mode)
        if not path.is_file():
            return policy
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidRuleError(f"{path} is not valid JSON: {exc}") from exc
        perms = data.get("permissions", {}) if isinstance(data, dict) else {}
        for kind in ("allow", "ask", "deny"):
            entries = perms.get(kind, [])
            if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
                raise InvalidRuleError(f"permissions.{kind} in {path} must be a list of strings")
            getattr(policy, kind).extend(Rule.parse(e) for e in entries)
        return policy

    def decide(self, tool: str, summary: str) -> Decision:
        if any(r.matches(tool, summary) for r in self.deny):
            return "deny"
        if any(r.matches(tool, summary) for r in self.allow):
            return "allow"
        if any(r.matches(tool, summary) for r in self.ask):
            return "allow" if self.mode == "allow-all" else "ask"
        if tool in AUTO_ALLOWED or self.mode == "allow-all":
            return "allow"
        if tool in EDIT_TOOLS and self.mode == "accept-edits":
            return "allow"
        return "ask"

    def allow_for_session(self, rule: Rule) -> None:
        """Adds an allow rule for the rest of this run (not written to settings)."""
        if rule not in self.allow:
            self.allow.append(rule)
