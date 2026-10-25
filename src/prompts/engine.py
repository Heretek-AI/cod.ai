"""
Unified Dual-Polarity Prompt Assembly Engine (`/src/prompts/engine.py`).
Supports:
  - Byte-identical static Layer 1 system prompt (modeled on Pi's 20-line static prefix + deferred tool catalog).
  - Layer 2 static project context (`CLAUDE.md` / `AGENTS.md` + active Skills Playbooks).
  - Layer 3 dynamic polarity & specialist charter switching (Mode A Holistic Web Architect vs.
    Mode B Surgical CLI Implementer vs. `@heretek-ai/pi-configs` Specialist Charters)
    WITHOUT ever mutating Layer 1 or Layer 2!
  - `COD_SIMPLE=true` 4-line minimal benchmark override.
"""
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.prompts.architect_mode import GoalPromptFrame, HolisticWebArchitectEngine
from src.prompts.implementer_mode import (
    DEDICATED_FILE_PRIMITIVES,
    AbstractionPolicy,
    BashAuditResult,
    validate_surgical_bash_command,
)
from src.prompts.simple_mode import build_simple_mode_prompt, is_simple_mode_enabled


class PolarityMode(str, Enum):
    MODE_A_ARCHITECT = "MODE_A_HOLISTIC_ARCHITECT"
    MODE_B_IMPLEMENTER = "MODE_B_SURGICAL_IMPLEMENTER"
    MODE_SIMPLE_BENCHMARK = "MODE_SIMPLE_BENCHMARK"


@dataclass(frozen=True)
class PiSpecialistConfig:
    """Loaded representation of an `@heretek-ai/pi-configs` specialist directory."""
    slug: str
    charter_markdown: str
    settings: dict[str, Any]
    hooks_yaml: str
    skills: dict[str, str] = field(default_factory=dict)


class PromptAssemblyEngine:
    """
    Assembles prompts for `cod.ai` while enforcing Invariant #1 (Byte-Identical Static Prefix)
    and Invariant #3 (Dual-Polarity Mode Switching).
    """

    def __init__(
        self,
        workspace_root: str,
        skills_root: str | None = None,
        pi_specialists_root: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.skills_root = Path(skills_root) if skills_root else self.workspace_root / "skills"
        self.pi_specialists_root = (
            Path(pi_specialists_root)
            if pi_specialists_root
            else self.workspace_root / "pi_configs_upstream" / "agents"
        )
        self.env = env if env is not None else dict(os.environ)
        self.architect_engine = HolisticWebArchitectEngine()
        self._locked_layer1_hash: str | None = None

    def build_static_layer1_system_prompt(
        self,
        core_tools: tuple[str, ...] = DEDICATED_FILE_PRIMITIVES,
        deferred_tool_names: list[str] | None = None,
    ) -> str:
        """
        Builds Layer 1 (System Prompt + Deferred Tool Directory).
        Modeled on Pi's ~20-line cache-disciplined prompt: ZERO timestamps, ZERO random IDs,
        and ZERO volatile session state so the prefix hash never changes across turns.
        If `COD_SIMPLE=true`, returns the 4-line minimal prompt.
        """
        if is_simple_mode_enabled(self.env):
            prompt = build_simple_mode_prompt(
                cwd=str(self.workspace_root),
                fixed_date=self.env.get("COD_FIXED_DATE", "2026-10-24"),
            )
            self._verify_or_lock_layer1(prompt)
            return prompt

        deferred = sorted(deferred_tool_names or [])
        deferred_line = ", ".join(deferred) if deferred else "none"
        core_line = ", ".join(core_tools)

        lines = [
            "You are cod.ai, a next-generation dual-polarity agentic coding harness and orchestration platform.",
            "Core Invariant 1: Preserve byte-identical static prefixes across Layer 1 and Layer 2.",
            "Core Invariant 2: Discover deferred tools on demand via ToolSearch; never dump unused schemas into Layer 1.",
            "Core Invariant 3: Operate in Mode A (Holistic Web Architect) for design/greenfield synthesis and Mode B (Surgical CLI Implementer) for repository execution.",
            "Core Invariant 4: Maintain context utilization within the 60-80% Attention Budget Governor ceiling.",
            "Core Invariant 5: Delegate multi-query (>3 Glob/Grep) discovery to the read-only Explore sub-agent and verify via the Adversarial Verifier.",
            "Core Invariant 6: Route all tool executions through the local security policy proxy and respect allow/soft_deny rules.",
            f"Active Core Primitives (non-deferred): {core_line}, ToolSearch",
            f"Deferred Tool Catalog (load via ToolSearch): {deferred_line}",
            f"Workspace Root: {self.workspace_root}",
        ]
        prompt = "\n".join(lines)
        self._verify_or_lock_layer1(prompt)
        return prompt

    def _verify_or_lock_layer1(self, prompt: str) -> None:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if self._locked_layer1_hash is None:
            self._locked_layer1_hash = digest
        elif self._locked_layer1_hash != digest:
            raise RuntimeError(
                f"Invariant #1 Violation: Layer 1 system prompt hash mutated mid-session "
                f"(expected {self._locked_layer1_hash}, got {digest})!"
            )

    def load_skill_playbook(self, domain: str) -> str:
        """Loads `/skills/<domain>/SKILL.md`."""
        skill_path = self.skills_root / domain / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill playbook not found: {skill_path}")
        return skill_path.read_text(encoding="utf-8").strip()

    def load_pi_specialist(self, slug: str) -> PiSpecialistConfig:
        """Loads an `@heretek-ai/pi-configs` specialist from `agents/<slug>/`."""
        agent_dir = self.pi_specialists_root / slug
        if not agent_dir.exists():
            raise FileNotFoundError(f"Pi specialist '{slug}' not found at {agent_dir}")

        charter_path = agent_dir / "AGENTS.md"
        settings_path = agent_dir / ".pi" / "settings.json"
        hooks_path = agent_dir / ".pi" / "hook" / "hooks.yaml"
        skills_dir = agent_dir / ".pi" / "skills"

        charter = charter_path.read_text(encoding="utf-8") if charter_path.exists() else ""
        settings = (
            json.loads(settings_path.read_text(encoding="utf-8"))
            if settings_path.exists()
            else {}
        )
        hooks = hooks_path.read_text(encoding="utf-8") if hooks_path.exists() else ""
        loaded_skills: dict[str, str] = {}
        if skills_dir.exists():
            for sfile in skills_dir.glob("*/SKILL.md"):
                loaded_skills[sfile.parent.name] = sfile.read_text(encoding="utf-8")

        return PiSpecialistConfig(
            slug=slug,
            charter_markdown=charter,
            settings=settings,
            hooks_yaml=hooks,
            skills=loaded_skills,
        )

    def build_layer3_polarity_switch(
        self,
        mode: PolarityMode,
        context: str,
        objective: str,
        project_instructions: str = "",
        skill_domains: list[str] | None = None,
        pi_specialist_slug: str | None = None,
        architect_authorized_abstractions: bool = False,
    ) -> str:
        """
        Generates a Layer 3 `<system_reminder>` / mid-conversation `role: "system"` payload
        that switches the agent between Mode A (Holistic Web Architect), Mode B (Surgical CLI Implementer),
        or a specific `@heretek-ai/pi-configs` specialist WITHOUT mutating Layer 1 or Layer 2.
        """
        playbooks = [self.load_skill_playbook(d) for d in (skill_domains or [])]
        specialist_block = ""
        if pi_specialist_slug:
            spec = self.load_pi_specialist(pi_specialist_slug)
            specialist_block = (
                f'\n<pi_specialist_charter slug="{spec.slug}">\n'
                f"{spec.charter_markdown.strip()}\n"
                f"</pi_specialist_charter>"
            )

        if mode == PolarityMode.MODE_A_ARCHITECT:
            goal_frame: GoalPromptFrame = self.architect_engine.build_goal_prompt(
                context=context,
                objective=objective,
                skills_playbooks=playbooks,
            )
            return (
                f'<system_reminder polarity="{mode.value}">\n'
                f"{goal_frame.render_xml()}"
                f"{specialist_block}\n"
                f"</system_reminder>"
            )

        if mode == PolarityMode.MODE_B_IMPLEMENTER:
            policy = AbstractionPolicy.from_project_instructions(
                project_instructions, architect_authorized=architect_authorized_abstractions
            )
            playbooks_xml = (
                "\n<skills_playbooks>\n" + "\n\n".join(playbooks) + "\n</skills_playbooks>"
                if playbooks
                else ""
            )
            return (
                f'<system_reminder polarity="{mode.value}">\n'
                f"<surgical_cli_mandate>\n"
                f"1. Use ONLY dedicated file primitives ({', '.join(DEDICATED_FILE_PRIMITIVES)}) for reading, searching, and editing files.\n"
                f"2. Raw Bash commands (`cat`, `head`, `tail`, `sed`, `awk`, `grep`, `find`, `>`) for file manipulation are strictly FORBIDDEN.\n"
                f"</surgical_cli_mandate>\n"
                f"{policy.render_policy_block()}"
                f"{playbooks_xml}"
                f"{specialist_block}\n"
                f"<objective>\n{objective.strip()}\n</objective>\n"
                f"</system_reminder>"
            )

        return f'<system_reminder polarity="{mode.value}">{objective.strip()}</system_reminder>'

    def audit_bash_tool_call(self, mode: PolarityMode, command: str) -> BashAuditResult:
        """Enforces Mode A (no raw Bash) and Mode B (no file-manipulation Bash) tool rules."""
        if mode == PolarityMode.MODE_A_ARCHITECT:
            return BashAuditResult(
                allowed=False,
                violating_command="Bash (in Mode A)",
                remediation="Mode A (Holistic Web Architect) forbids Bash execution to preserve n^2 self-attention purity. Switch to Mode B for test/build execution.",
            )
        return validate_surgical_bash_command(command)
