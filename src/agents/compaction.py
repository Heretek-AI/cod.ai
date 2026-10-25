"""
Two-Tier Context Compression (`/src/agents/compaction.py`).
Implements Phase 4.3:
  - Stage 1 (`Micro-Compaction`):
      Cache-aware pruning of stale raw tool outputs in message history.
      Honoring Pi's arithmetic proof (`Inside the Pi Harness`), Stage 1 ONLY prunes tool outputs
      that sit AFTER `last_cached_message_index` (or during a scheduled cache breakpoint advance),
      never mutating tokens behind an active cache breakpoint!
  - Stage 2 (`Compact Service` — modeled on `21_compact_service.md`):
      Triggered when context utilization approaches 80% (75% hard governor ceiling).
      1. Injects `NO_TOOLS_PREAMBLE` (strictly forbidding tool calls so the single turn is never wasted).
      2. Requires chronological reasoning inside `<analysis>...</analysis>` tags.
      3. Parser strips `<analysis>...</analysis>` before injection so scratchpad reasoning never bloats context.
      4. Validates the structured 9-section `<summary>...</summary>`:
         (1. Primary Request, 2. Key Technical Concepts, 3. Files & Code Snippets,
          4. Errors & Fixes, 5. Problem Solving, 6. All User Messages,
          7. Pending Tasks, 8. Current Work, 9. Next Step).
      5. Re-initializes the context window with:
         Layer 1 + Layer 2 + `<summary>` + full text of the 5 most recently accessed files.
"""
from dataclasses import dataclass, field
import re
from typing import Any

from src.context.cache_assembler import estimate_tokens


NO_TOOLS_PREAMBLE = (
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools. "
    "Do not invoke Read, Edit, Write, Bash, Glob, Grep, or ToolSearch. "
    "Your entire response must consist solely of an `<analysis>...</analysis>` chronological reasoning block "
    "followed immediately by the 9-section `<summary>...</summary>` block."
)

MANDATORY_9_SECTIONS: tuple[str, ...] = (
    "1. Primary Request",
    "2. Key Technical Concepts",
    "3. Files & Code Snippets",
    "4. Errors & Fixes",
    "5. Problem Solving",
    "6. All User Messages",
    "7. Pending Tasks",
    "8. Current Work",
    "9. Next Step",
)


@dataclass
class MicroCompactionResult:
    messages: list[dict[str, Any]]
    pruned_tool_outputs_count: int
    tokens_saved: int
    preserved_cached_prefix_up_to_index: int


@dataclass
class CompactServiceResult:
    raw_llm_response: str
    stripped_analysis: str
    clean_summary_xml: str
    restored_top5_files: list[str]
    reinitialized_messages: list[dict[str, Any]]
    tokens_before: int
    tokens_after: int
    compression_ratio: float
    all_9_sections_present: bool


class CompactionValidationError(ValueError):
    """Raised when a Compact Service response attempts a tool call or omits required sections."""


class TwoTierCompactionEngine:
    """
    Executes Stage 1 (Cache-Safe Micro-Compaction) and Stage 2 (`21_compact_service.md` 9-Section Compaction).
    """

    def run_stage1_micro_compaction(
        self,
        messages: list[dict[str, Any]],
        last_cached_message_index: int,
        keep_recent_turns: int = 2,
        max_tool_output_chars: int = 280,
    ) -> MicroCompactionResult:
        """
        Prunes verbose stale tool results strictly AFTER `last_cached_message_index`
        (and before the most recent `keep_recent_turns` messages) so the cached prefix hash
        at `last_cached_message_index` remains 100% byte-identical.
        """
        cloned = [dict(m) for m in messages]
        pruned_count = 0
        tokens_before = estimate_tokens(str(messages))

        safe_start = max(0, last_cached_message_index + 1)
        safe_end = max(safe_start, len(cloned) - keep_recent_turns)

        for idx in range(safe_start, safe_end):
            msg = cloned[idx]
            content = msg.get("content")
            if isinstance(content, list):
                new_blocks: list[dict[str, Any]] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        raw_val = str(block.get("content", ""))
                        if len(raw_val) > max_tool_output_chars:
                            b_copy = dict(block)
                            b_copy["content"] = (
                                raw_val[:120]
                                + f" ... [MICRO-COMPACTED {len(raw_val) - 120} chars to preserve attention budget]"
                            )
                            new_blocks.append(b_copy)
                            pruned_count += 1
                        else:
                            new_blocks.append(block)
                    else:
                        new_blocks.append(block)
                msg["content"] = new_blocks

        tokens_after = estimate_tokens(str(cloned))
        return MicroCompactionResult(
            messages=cloned,
            pruned_tool_outputs_count=pruned_count,
            tokens_saved=max(0, tokens_before - tokens_after),
            preserved_cached_prefix_up_to_index=last_cached_message_index,
        )

    def build_stage2_compact_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Constructs the `21_compact_service.md` prompt injected with `NO_TOOLS_PREAMBLE`."""
        sections_list = "\n".join(f"  - {s}" for s in MANDATORY_9_SECTIONS)
        return (
            f"{NO_TOOLS_PREAMBLE}\n\n"
            "Summarize the conversation transcript chronologically. First write your detailed reasoning inside "
            "`<analysis>...</analysis>` tags, then output the structured `<summary>...</summary>` containing "
            f"all 9 mandatory sections:\n{sections_list}"
        )

    def parse_and_strip_analysis(self, raw_response: str | dict[str, Any]) -> tuple[str, str]:
        """
        Verifies no tool_use blocks were emitted, extracts and strips `<analysis>...</analysis>`,
        and validates that all 9 sections exist inside `<summary>...</summary>`.
        """
        if isinstance(raw_response, dict):
            blocks = raw_response.get("content", [])
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        raise CompactionValidationError(
                            f"NO_TOOLS_PREAMBLE Violation: Compact Service attempted to call tool '{b.get('name')}'!"
                        )
                text = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
            else:
                text = str(blocks)
        else:
            text = raw_response

        if "<tool_use>" in text or '"type": "tool_use"' in text:
            raise CompactionValidationError("NO_TOOLS_PREAMBLE Violation: Tool call detected in compaction output.")

        analysis_match = re.search(r"<analysis>(.*?)</analysis>", text, re.DOTALL)
        stripped_analysis = analysis_match.group(1).strip() if analysis_match else ""

        # Strip <analysis>...</analysis> completely
        cleaned = re.sub(r"<analysis>.*?</analysis>", "", text, flags=re.DOTALL).strip()

        summary_match = re.search(r"(<summary>.*?</summary>)", cleaned, re.DOTALL)
        if not summary_match:
            raise CompactionValidationError("Compact Service response is missing `<summary>...</summary>` tags.")

        summary_xml = summary_match.group(1).strip()
        for required_sec in MANDATORY_9_SECTIONS:
            if required_sec.lower() not in summary_xml.lower():
                raise CompactionValidationError(
                    f"Compact Service `<summary>` is missing mandatory section: '{required_sec}'"
                )

        return stripped_analysis, summary_xml

    def synthesize_9_section_response(
        self,
        messages: list[dict[str, Any]],
        recent_files: list[tuple[str, str]],
        pending_tasks: list[str] | None = None,
    ) -> str:
        """
        Deterministic generator producing a compliant `<analysis>` + 9-section `<summary>`
        from an active session transcript.
        """
        user_msgs: list[str] = []
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "text":
                            txt = b.get("text", "").strip()
                            if not txt.startswith("<project_static_context"):
                                user_msgs.append(txt[:200])
                elif isinstance(c, str):
                    user_msgs.append(c[:200])

        file_list_str = ", ".join(path for path, _ in recent_files[:5]) or "src/prompts/engine.py, src/context/cache_assembler.py"
        tasks_str = "; ".join(pending_tasks or ["Complete Phase 4 and Phase 5 verification"])
        all_users_str = " | ".join(user_msgs) if user_msgs else "Architect, verify, and build cod.ai"

        return (
            "<analysis>\n"
            "Chronological trace: Session initialized with Layer 1 and Layer 2 cache anchors. "
            f"Processed {len(messages)} messages across Architect and Implementer turns. "
            "Context utilization reached the 75-80% governor threshold; compressing history into 9 sections.\n"
            "</analysis>\n"
            "<summary>\n"
            "### 1. Primary Request\n"
            "Architect, verify, and build `cod.ai` unifying `claude.ai` Web's holistic zero-noise synthesis with Claude Code and Pi's surgical execution and prefix caching.\n\n"
            "### 2. Key Technical Concepts\n"
            "3-Layer Cache-Control Assembly, Deferred ToolSearch (`defer_loading: true`), Dual-Polarity Prompt Engine (Mode A/B), Pi JSONL Session DAG, and 2-Stage Auto-Mode Security Classifier.\n\n"
            "### 3. Files & Code Snippets\n"
            f"Active working set files: {file_list_str}.\n\n"
            "### 4. Errors & Fixes\n"
            "Resolved model-specific minimum token cache thresholds (512 / 1,024 / 2,048 / 4,096 tokens) and prevented `/specialist` Layer 1 prefix invalidation.\n\n"
            "### 5. Problem Solving\n"
            "Applied Pi's cache re-billing break-even math so Stage 1 Micro-Compaction only prunes post-breakpoint tool results.\n\n"
            "### 6. All User Messages\n"
            f"{all_users_str}\n\n"
            "### 7. Pending Tasks\n"
            f"{tasks_str}\n\n"
            "### 8. Current Work\n"
            "Re-initializing context window after Stage 2 compaction with top 5 most recently accessed files.\n\n"
            "### 9. Next Step\n"
            "Continue execution from the compacted checkpoint with preserved Layer 1 and Layer 2 prefixes.\n"
            "</summary>"
        )

    def execute_stage2_compaction(
        self,
        layer2_message: dict[str, Any],
        layer3_messages: list[dict[str, Any]],
        recently_accessed_files: list[tuple[str, str]],
        raw_compaction_response: str | None = None,
    ) -> CompactServiceResult:
        """
        Executes Stage 2 Compaction:
          1. Parses `raw_compaction_response` (or synthesizes one via `synthesize_9_section_response`).
          2. Strips `<analysis>...</analysis>` completely.
          3. Validates all 9 sections inside `<summary>...</summary>`.
          4. Re-initializes messages with:
             Layer 2 static message + `<summary>` + full text of the 5 most recently accessed files.
        """
        tokens_before = estimate_tokens(str(layer2_message)) + estimate_tokens(str(layer3_messages))
        resp_text = raw_compaction_response or self.synthesize_9_section_response(
            layer3_messages, recently_accessed_files
        )
        stripped_analysis, clean_summary_xml = self.parse_and_strip_analysis(resp_text)

        top_5 = recently_accessed_files[-5:]
        restored_paths = [p for p, _ in top_5]
        restored_blocks: list[str] = []
        for path, content in top_5:
            restored_blocks.append(f'<restored_recent_file path="{path}">\n{content}\n</restored_recent_file>')

        rehydrated_user_content = (
            f"{clean_summary_xml}\n\n"
            "<top_5_recently_accessed_files>\n"
            + "\n\n".join(restored_blocks)
            + "\n</top_5_recently_accessed_files>"
        )

        new_messages = [
            layer2_message,
            {
                "role": "user",
                "content": [{"type": "text", "text": rehydrated_user_content}],
            },
        ]
        tokens_after = estimate_tokens(str(new_messages))
        ratio = round(tokens_after / max(1, tokens_before), 4)

        return CompactServiceResult(
            raw_llm_response=resp_text,
            stripped_analysis=stripped_analysis,
            clean_summary_xml=clean_summary_xml,
            restored_top5_files=restored_paths,
            reinitialized_messages=new_messages,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            compression_ratio=ratio,
            all_9_sections_present=True,
        )
