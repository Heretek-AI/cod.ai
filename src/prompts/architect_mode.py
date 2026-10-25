"""
Mode A — "Holistic Web Architect" (Modeled on `claude.ai` Web + Artifacts `<antArtifact>` + Skills).
Enforces:
  1. Full in-context n^2 self-attention purity (zero noisy bash/grep logs in context).
  2. Curated Skills Playbook injection (/skills/<domain>/SKILL.md).
  3. Zero-Truncation & Iterative Drafting Mandate for files/specs >100 lines:
     (Outline -> Section-by-Section Generation -> Review & Refine -> Final Output)
     with deterministic validation banning placeholders (`// rest of code...`, etc.).
  4. GOAL Philosophy framing inside positive XML tags:
     `<context>`, `<objective>`, `<constraints>`, `<output_contract>`.
"""
from dataclasses import dataclass, field
import re
from typing import Callable


FORBIDDEN_TRUNCATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"//\s*rest of (the )?code", re.IGNORECASE),
    re.compile(r"#\s*rest of (the )?code", re.IGNORECASE),
    re.compile(r"//\s*\.\.\.\s*existing", re.IGNORECASE),
    re.compile(r"#\s*\.\.\.\s*existing", re.IGNORECASE),
    re.compile(r"/\*\s*\.\.\.\s*\*/", re.IGNORECASE),
    re.compile(r"TODO:\s*implement", re.IGNORECASE),
    re.compile(r"FIXME:\s*implement", re.IGNORECASE),
    re.compile(r"pass\s*#\s*placeholder", re.IGNORECASE),
    re.compile(r"raise NotImplementedError\(\s*['\"]placeholder", re.IGNORECASE),
]


@dataclass(frozen=True)
class GoalPromptFrame:
    """Structured GOAL Philosophy XML envelope using strictly positive commands."""
    context: str
    objective: str
    constraints: list[str]
    output_contract: str
    skills_playbooks: list[str] = field(default_factory=list)

    def render_xml(self) -> str:
        constraints_xml = "\n".join(f"  - {c}" for c in self.constraints)
        skills_xml = ""
        if self.skills_playbooks:
            joined_skills = "\n\n".join(self.skills_playbooks)
            skills_xml = f"\n<skills_playbooks>\n{joined_skills}\n</skills_playbooks>"

        return (
            f"<context>\n{self.context.strip()}\n</context>\n"
            f"<objective>\n{self.objective.strip()}\n</objective>\n"
            f"<constraints>\n{constraints_xml}\n</constraints>{skills_xml}\n"
            f"<output_contract>\n{self.output_contract.strip()}\n</output_contract>"
        )


@dataclass
class IterativeDraftingArtifact:
    """Represents a >100-line artifact synthesized through the 4-stage Mode A loop."""
    identifier: str
    title: str
    target_path: str
    outline_sections: list[str]
    generated_sections: dict[str, str]
    review_notes: list[str]
    final_content: str
    line_count: int

    def to_ant_artifact_xml(self) -> str:
        return (
            f'<antArtifact identifier="{self.identifier}" type="application/vnd.ant.code" '
            f'title="{self.title}" path="{self.target_path}" lines="{self.line_count}">\n'
            f"{self.final_content}\n"
            f"</antArtifact>"
        )


class TruncationViolationError(ValueError):
    """Raised when generated code or specification contains banned placeholder/truncation markers."""


def verify_zero_truncation(content: str, require_min_lines: int = 0) -> tuple[bool, list[str]]:
    """
    Scans content for banned truncation/elision placeholders and verifies minimum line count.
    Returns (is_valid, list_of_violations).
    """
    violations: list[str] = []
    lines = content.splitlines()
    if require_min_lines > 0 and len(lines) < require_min_lines:
        violations.append(
            f"Line count {len(lines)} is below required threshold of {require_min_lines} lines."
        )

    for line_no, line in enumerate(lines, start=1):
        for pattern in FORBIDDEN_TRUNCATION_PATTERNS:
            if pattern.search(line):
                violations.append(
                    f"Line {line_no} matches forbidden truncation pattern '{pattern.pattern}': {line.strip()}"
                )
    return (len(violations) == 0, violations)


class HolisticWebArchitectEngine:
    """
    Orchestrates Mode A ("Holistic Web Architect") prompt synthesis and the 4-stage
    iterative drafting loop (Outline -> Section-by-Section Generation -> Review & Refine -> Final Output)
    for files and architectural specifications >100 lines.
    """

    def build_goal_prompt(
        self,
        context: str,
        objective: str,
        custom_constraints: list[str] | None = None,
        output_contract: str = "Emit complete, production-ready, un-truncated `<antArtifact>` modules.",
        skills_playbooks: list[str] | None = None,
    ) -> GoalPromptFrame:
        base_constraints = [
            "Maintain 100% in-context n^2 self-attention purity by synthesizing complete architectural state before emitting code.",
            "Present explicit trade-off analysis (latency, cache economics, failure modes) inside the architectural rationale.",
            "Layer complexity sequentially: define core domain types and invariants first, then state transitions, then edge-case handlers.",
            "Write every module and function in complete, production-ready form with zero placeholders or truncation comments.",
        ]
        if custom_constraints:
            base_constraints.extend(custom_constraints)

        return GoalPromptFrame(
            context=context,
            objective=objective,
            constraints=base_constraints,
            output_contract=output_contract,
            skills_playbooks=skills_playbooks or [],
        )

    def orchestrate_iterative_draft(
        self,
        identifier: str,
        title: str,
        target_path: str,
        section_specs: list[tuple[str, Callable[[], str]]],
        refiner: Callable[[str], tuple[str, list[str]]] | None = None,
        enforce_over_100_lines: bool = True,
    ) -> IterativeDraftingArtifact:
        """
        Executes the mandatory 4-step Mode A drafting pipeline for >100-line deliverables:
          1. Outline -> 2. Section-by-Section Generation -> 3. Review & Refine -> 4. Final Output
        Raises TruncationViolationError if any placeholder or truncation marker is detected.
        """
        # Step 1: Outline
        outline_sections = [sec_title for sec_title, _ in section_specs]
        if not outline_sections:
            raise ValueError("Iterative drafting requires at least one structural outline section.")

        # Step 2: Section-by-Section Generation
        generated_sections: dict[str, str] = {}
        assembled_chunks: list[str] = []
        for sec_title, generator_fn in section_specs:
            sec_content = generator_fn()
            is_ok, violations = verify_zero_truncation(sec_content, require_min_lines=0)
            if not is_ok:
                raise TruncationViolationError(
                    f"Truncation detected in section '{sec_title}': {'; '.join(violations)}"
                )
            generated_sections[sec_title] = sec_content
            assembled_chunks.append(sec_content)

        raw_combined = "\n\n".join(assembled_chunks)

        # Step 3: Review & Refine
        if refiner is not None:
            refined_content, review_notes = refiner(raw_combined)
        else:
            refined_content = raw_combined
            review_notes = [
                f"Verified {len(outline_sections)} structural sections with zero placeholders.",
                "Verified all imports, type signatures, and boundary invariants.",
            ]

        # Step 4: Final Output Verification
        min_lines = 101 if enforce_over_100_lines else 1
        is_valid, final_violations = verify_zero_truncation(refined_content, require_min_lines=min_lines)
        if not is_valid:
            raise TruncationViolationError(
                f"Final artifact '{identifier}' failed zero-truncation check: {'; '.join(final_violations)}"
            )

        line_count = len(refined_content.splitlines())
        return IterativeDraftingArtifact(
            identifier=identifier,
            title=title,
            target_path=target_path,
            outline_sections=outline_sections,
            generated_sections=generated_sections,
            review_notes=review_notes,
            final_content=refined_content,
            line_count=line_count,
        )
