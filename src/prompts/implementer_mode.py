"""
Mode B — "Surgical CLI Implementer" (Modeled on Claude Code + Override Tunings).
Enforces:
  1. Dedicated file primitives (`Read`, `Edit`, `Write`, `Glob`, `Grep`) for all file operations.
  2. Strict ban on raw `Bash` file-manipulation commands (`cat`, `head`, `tail`, `sed`, `awk`, `perl -pi`, `echo >`)
     so that all file reads and diffs are structured, auditable, and cache-governed.
  3. Neutralization of Claude Code's default anti-abstraction handicap when authorized by `CLAUDE.md` /
     `AGENTS.md` or the Mode A Architect spec (explicitly permitting modular helpers, comprehensive boundary
     validation, and clean abstractions).
"""
from dataclasses import dataclass
import re
import shlex


DEDICATED_FILE_PRIMITIVES: tuple[str, ...] = ("Read", "Edit", "Write", "Glob", "Grep")

# Regex patterns catching raw Bash file manipulation commands across pipe/chain segments
FORBIDDEN_BASH_FILE_COMMANDS: dict[str, str] = {
    "cat": "Use the dedicated `Read` primitive instead of `cat` to inspect files.",
    "head": "Use the dedicated `Read` primitive (with offset/limit) instead of `head`.",
    "tail": "Use the dedicated `Read` primitive (with offset/limit) instead of `tail`.",
    "sed": "Use the dedicated `Edit` primitive instead of `sed` so all diffs are structured and auditable.",
    "awk": "Use the dedicated `Edit` or `Read` primitive instead of `awk` for file manipulation.",
    "grep": "Use the dedicated `Grep` primitive instead of raw bash `grep`/`rg`.",
    "rg": "Use the dedicated `Grep` primitive instead of raw bash `rg`.",
    "find": "Use the dedicated `Glob` primitive instead of raw bash `find`.",
    "fd": "Use the dedicated `Glob` primitive instead of raw bash `fd`.",
}


@dataclass(frozen=True)
class AbstractionPolicy:
    """
    Controls whether Claude Code's default anti-abstraction rules are neutralized
    by `CLAUDE.md` / `AGENTS.md` or an upstream Mode A Architect specification.
    """
    allow_modular_helpers: bool = False
    allow_boundary_validation: bool = False
    allow_clean_abstractions: bool = False
    source_directive: str = "default_surgical_minimal"

    @classmethod
    def from_project_instructions(cls, project_markdown: str, architect_authorized: bool = False) -> "AbstractionPolicy":
        text_lower = project_markdown.lower()
        helpers = architect_authorized or ("authorize_modular_helpers" in text_lower) or ("allow modular helpers" in text_lower)
        validation = architect_authorized or ("authorize_boundary_validation" in text_lower) or ("comprehensive boundary validation" in text_lower)
        abstractions = architect_authorized or ("authorize_clean_abstractions" in text_lower) or ("clean abstractions" in text_lower)
        source = "architect_and_agents_md_override" if (helpers or validation or abstractions) else "default_surgical_minimal"
        return cls(
            allow_modular_helpers=helpers,
            allow_boundary_validation=validation,
            allow_clean_abstractions=abstractions,
            source_directive=source,
        )

    def render_policy_block(self) -> str:
        if self.allow_modular_helpers or self.allow_boundary_validation or self.allow_clean_abstractions:
            return (
                '<abstraction_authorization status="AUTHORIZED_BY_ARCHITECT_OR_AGENTS_MD">\n'
                "The default CLI anti-abstraction handicap is NEUTRALIZED for this session:\n"
                f"- Modular Helpers Authorized: {self.allow_modular_helpers}\n"
                f"- Comprehensive Boundary Validation Authorized: {self.allow_boundary_validation}\n"
                f"- Clean Domain Abstractions Authorized: {self.allow_clean_abstractions}\n"
                "Build cohesive, well-factored helper modules and explicit input/output boundary validators as specified.\n"
                "</abstraction_authorization>"
            )
        return (
            '<abstraction_authorization status="SURGICAL_MINIMAL">\n'
            "Focus strictly on surgical modifications to existing files. Avoid unrequested abstractions unless authorized by Mode A Architect specs or CLAUDE.md/AGENTS.md.\n"
            "</abstraction_authorization>"
        )


@dataclass(frozen=True)
class BashAuditResult:
    allowed: bool
    violating_command: str | None = None
    remediation: str | None = None


def split_shell_pipeline(command: str) -> list[str]:
    """Splits a shell command string across `|`, `&&`, `||`, and `;` operators."""
    return [seg.strip() for seg in re.split(r"\|\||&&|[|;]", command) if seg.strip()]


def validate_surgical_bash_command(command: str) -> BashAuditResult:
    """
    Audits a proposed Bash command in Mode B (Surgical CLI Implementer).
    Blocks raw file manipulation (`cat`, `head`, `tail`, `sed`, `awk`, `grep`, `find`, or `>` file redirects)
    so that all file inspection and editing flows through `Read`, `Edit`, `Write`, `Glob`, and `Grep`.
    """
    segments = split_shell_pipeline(command)
    for seg in segments:
        # Check for raw file overwrite redirection (excluding /dev/null or fd duplication like 2>&1)
        cleaned_redirects = re.sub(r"[0-9]*>&[0-9]+|>[> ]*/dev/null", "", seg)
        if re.search(r"(^|\s)>>?\s*[^\s&]+", cleaned_redirects):
            return BashAuditResult(
                allowed=False,
                violating_command="shell_redirection (> / >>)",
                remediation="Use the dedicated `Write` or `Edit` primitive instead of shell output redirection (`>` or `>>`) to modify files.",
            )

        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()

        if not tokens:
            continue

        # Skip leading ENV=val assignments
        cmd_idx = 0
        while cmd_idx < len(tokens) and "=" in tokens[cmd_idx] and not tokens[cmd_idx].startswith("-"):
            cmd_idx += 1
        if cmd_idx >= len(tokens):
            continue

        executable = tokens[cmd_idx].rsplit("/", 1)[-1]
        if executable in FORBIDDEN_BASH_FILE_COMMANDS:
            return BashAuditResult(
                allowed=False,
                violating_command=executable,
                remediation=FORBIDDEN_BASH_FILE_COMMANDS[executable],
            )

    return BashAuditResult(allowed=True)
