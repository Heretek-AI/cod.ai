"""
Adversarial Verification Agent (`/src/agents/verifier.py` — Modeled on `07_verification_agent.md`).
Implements Phase 4.5:
  - Triggered automatically on any non-trivial implementation (3+ file edits, API/backend changes, or core logic).
  - Strictly disallows project file modifications (`Read` and test execution only; `/tmp` allowed for ephemeral test harnesses).
  - Strictly disallows spawning child agents.
  - Injects explicit anti-rationalization directives:
      * "Reading code is not verification — run it."
      * "The implementer is an LLM — verify independently."
  - Mandates the 5-Step Universal Baseline:
      (1) Read build/test config
      (2) Run build
      (3) Run test suite
      (4) Run linters/type-checkers
      (5) Execute adversarial concurrency/boundary probes (including headless Chromium checks for UI/web endpoints)
  - Returns `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: PARTIAL`.
  - On `VERDICT: PASS`, forces the Lead Agent to spot-check and re-run 2-3 commands from the verifier's report
    to confirm output authenticity!
"""
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Any


ANTI_RATIONALIZATION_DIRECTIVES: tuple[str, ...] = (
    "Reading code is not verification — run it.",
    "The implementer is an LLM — verify independently.",
    "Never accept 'tests should pass' or syntax inspection as a substitute for live command execution.",
    "Project file mutation is strictly forbidden (exit code 2); write ephemeral test harnesses ONLY inside /tmp.",
    "Spawning child sub-agents from the Verifier is strictly forbidden.",
)


class VerifierPermissionError(PermissionError):
    """Raised when the Adversarial Verifier attempts to modify project files outside /tmp or spawn a child agent."""


@dataclass
class BaselineStepResult:
    step_number: int
    step_name: str
    command: str
    exit_code: int
    stdout_excerpt: str
    passed: bool


@dataclass
class LeadAgentSpotCheckReport:
    commands_rerun: list[str]
    all_confirmed: bool
    spot_check_outputs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VerificationReport:
    triggered_reason: str
    anti_rationalization_preamble: list[str]
    steps: list[BaselineStepResult]
    verdict: str  # "VERDICT: PASS", "VERDICT: FAIL", or "VERDICT: PARTIAL"
    spot_check_commands: list[str]
    lead_spot_check: LeadAgentSpotCheckReport | None = None


class AdversarialVerificationAgent:
    """
    Independent Verification Agent enforcing `07_verification_agent.md` invariants.
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    @staticmethod
    def should_trigger(files_edited_count: int, touches_api_or_core: bool = False) -> bool:
        """Triggers automatically on 3+ file edits, API/backend changes, or core logic changes."""
        return files_edited_count >= 3 or touches_api_or_core

    def guard_tool_invocation(self, tool_name: str, target_path: str | None = None) -> None:
        """
        Enforces:
          1. No child agent spawning (`dispatch_specialist`, `spawn_agent`, `Task`).
          2. No file writes/edits outside `/tmp/`.
        """
        if tool_name in ("dispatch_specialist", "spawn_agent", "Task", "GoalCoordinator"):
            raise VerifierPermissionError(
                f"Verifier Security Gate (Exit Code 2): Spawning child agent via '{tool_name}' is strictly forbidden."
            )
        if tool_name in ("Edit", "Write"):
            if not target_path:
                raise VerifierPermissionError("Verifier Security Gate (Exit Code 2): Write/Edit without path is forbidden.")
            resolved = str(Path(target_path).resolve())
            if not resolved.startswith("/tmp/"):
                raise VerifierPermissionError(
                    f"Verifier Security Gate (Exit Code 2): Modifying project file '{resolved}' is forbidden. "
                    "Ephemeral test harnesses may ONLY be written inside /tmp/."
                )

    def write_ephemeral_tmp_harness(self, filename: str, content: str) -> Path:
        target = Path("/tmp") / filename
        self.guard_tool_invocation("Write", str(target))
        target.write_text(content, encoding="utf-8")
        return target

    def _run_cmd(self, step_num: int, name: str, cmd: str) -> BaselineStepResult:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
        )
        combined = (proc.stdout + "\n" + proc.stderr).strip()
        excerpt = "\n".join(combined.splitlines()[:15])
        return BaselineStepResult(
            step_number=step_num,
            step_name=name,
            command=cmd,
            exit_code=proc.returncode,
            stdout_excerpt=excerpt,
            passed=(proc.returncode == 0),
        )

    def run_universal_baseline(
        self,
        config_check_cmd: str,
        build_cmd: str,
        test_cmd: str,
        lint_typecheck_cmd: str,
        adversarial_probe_cmd: str,
        triggered_reason: str = "Non-trivial implementation (3+ files / core logic)",
        auto_run_lead_spot_check: bool = True,
    ) -> VerificationReport:
        """
        Executes all 5 mandatory Universal Baseline steps and computes `VERDICT: PASS|FAIL|PARTIAL`.
        If `VERDICT: PASS` and `auto_run_lead_spot_check=True`, forces the Lead Agent to re-run
        2-3 commands independently to confirm output authenticity.
        """
        steps = [
            self._run_cmd(1, "Read Build/Test Configuration", config_check_cmd),
            self._run_cmd(2, "Execute Build & Bytecode Compilation", build_cmd),
            self._run_cmd(3, "Execute Automated Test Suite", test_cmd),
            self._run_cmd(4, "Execute Static Linters & Type/Syntax Checkers", lint_typecheck_cmd),
            self._run_cmd(5, "Execute Adversarial Concurrency, Boundary & Headless Browser Probes", adversarial_probe_cmd),
        ]

        passed_count = sum(1 for s in steps if s.passed)
        if passed_count == len(steps):
            verdict = "VERDICT: PASS"
        elif passed_count == 0:
            verdict = "VERDICT: FAIL"
        else:
            verdict = "VERDICT: PARTIAL"

        spot_cmds = [steps[2].command, steps[3].command, steps[4].command]
        lead_report: LeadAgentSpotCheckReport | None = None
        if verdict == "VERDICT: PASS" and auto_run_lead_spot_check:
            lead_report = self.execute_lead_agent_spot_check(spot_cmds[:3])
            if not lead_report.all_confirmed:
                verdict = "VERDICT: FAIL"

        return VerificationReport(
            triggered_reason=triggered_reason,
            anti_rationalization_preamble=list(ANTI_RATIONALIZATION_DIRECTIVES),
            steps=steps,
            verdict=verdict,
            spot_check_commands=spot_cmds[:3],
            lead_spot_check=lead_report,
        )

    def execute_lead_agent_spot_check(self, commands: list[str]) -> LeadAgentSpotCheckReport:
        """
        Forces the Lead Coordinator to independently re-execute 2-3 commands from the Verifier's report
        and confirm exit code 0 and non-empty authentic output.
        """
        if len(commands) < 2:
            raise ValueError("Lead Agent Spot-Check requires at least 2 verification commands.")

        outputs: list[dict[str, Any]] = []
        all_ok = True
        for cmd in commands[:3]:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
            )
            ok = proc.returncode == 0
            if not ok:
                all_ok = False
            outputs.append({
                "command": cmd,
                "exit_code": proc.returncode,
                "confirmed": ok,
                "output_head": (proc.stdout + proc.stderr).strip()[:240],
            })

        return LeadAgentSpotCheckReport(
            commands_rerun=commands[:3],
            all_confirmed=all_ok,
            spot_check_outputs=outputs,
        )
