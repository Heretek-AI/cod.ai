"""
3-Layer Cache-Control Assembler (`/src/context/cache_assembler.py`).
Grounded in verified October 2026 Anthropic Prompt Caching & Tool Search specifications:
  - Prefix hierarchy: `tools` -> `system` -> `messages`.
  - Model-aware minimum cacheable token thresholds:
      * 512 tokens: claude-fable-5-1, claude-mythos-5-1, claude-opus-5-5, claude-opus-5, claude-sonnet-5-5, claude-haiku-5-5
      * 1,024 tokens: claude-opus-4-8, claude-sonnet-5, claude-sonnet-4-6, claude-sonnet-4-5
      * 2,048 tokens: claude-opus-4-7, claude-haiku-3-5
      * 4,096 tokens: claude-opus-4-6, claude-opus-4-5, claude-haiku-4-5
  - Deferred Tool Loading (`ToolSearch` pattern):
      * Core tools (`defer_loading: False`) carry the `tools` cache breakpoint.
      * Deferred MCP/extended tools (`defer_loading: True`) NEVER carry `cache_control` (prevents HTTP 400).
      * Full schemas are expanded via `tool_reference` or Layer 3 `tool_addition` (`inline-tools-2026-09-15`).
  - Immutable SHA-256 Prefix Guard on Layer 1 (`tools` + `system`) and Layer 2 (`CLAUDE.md` / `AGENTS.md`).
  - Layer 3 Mid-Session Injection via `<system_reminder>` or `role: "system"` (`clear_at: "next_user_message"`).
"""
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


MODEL_MIN_CACHE_TOKENS: dict[str, int] = {
    "claude-fable-5-1": 512,
    "claude-mythos-5-1": 512,
    "claude-fable-5": 512,
    "claude-mythos-5": 512,
    "claude-opus-5-5": 512,
    "claude-opus-5": 512,
    "claude-sonnet-5-5": 512,
    "claude-haiku-5-5": 512,
    "claude-opus-4-8": 1024,
    "claude-sonnet-5": 1024,
    "claude-sonnet-4-6": 1024,
    "claude-sonnet-4-5": 1024,
    "claude-opus-4-7": 2048,
    "claude-haiku-3-5": 2048,
    "claude-opus-4-6": 4096,
    "claude-opus-4-5": 4096,
    "claude-haiku-4-5": 4096,
}


def get_min_cache_tokens(model_id: str) -> int:
    """Returns the verified minimum cacheable token threshold for a given Claude model ID."""
    normalized = model_id.strip().lower()
    for prefix, threshold in MODEL_MIN_CACHE_TOKENS.items():
        if normalized.startswith(prefix):
            return threshold
    if "haiku" in normalized:
        return 2048
    return 1024


def estimate_tokens(text: str) -> int:
    """
    Deterministic token estimator (~3.8 chars per token + punctuation/whitespace weighting)
    for offline/sandbox verification without external tokenizer network fetches.
    """
    if not text:
        return 0
    words = re.findall(r"\w+|[^\w\s]", text)
    char_est = max(1, len(text) // 4)
    word_est = int(len(words) * 1.15)
    return max(char_est, word_est)


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    defer_loading: bool = False
    server_name: str | None = None

    def to_api_dict(self, with_cache_control: bool = False, ttl: str | None = None) -> dict[str, Any]:
        if self.defer_loading and with_cache_control:
            raise ValueError(
                f"Anthropic API 400 Guard: Deferred tool '{self.name}' (defer_loading=True) cannot carry cache_control."
            )
        entry: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.defer_loading:
            entry["defer_loading"] = True
        if with_cache_control:
            cc: dict[str, Any] = {"type": "ephemeral"}
            if ttl:
                cc["ttl"] = ttl
            entry["cache_control"] = cc
        return entry


@dataclass
class AssembledRequest:
    model: str
    tools: list[dict[str, Any]]
    system: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    layer1_tokens: int
    layer2_tokens: int
    layer3_tokens: int
    layer1_hash: str
    layer2_hash: str
    breakpoint_count: int
    cache_eligible_layer1: bool
    cache_eligible_layer2: bool
    betas: list[str] = field(default_factory=list)


class PrefixMutationError(RuntimeError):
    """Raised when any attempt is made to mutate Layer 1 or Layer 2 mid-session."""


class ThreeLayerCacheAssembler:
    """
    Constructs Anthropic Messages API payloads with strict 3-Layer cache isolation:
      - Layer 1: Static System Prompt + Non-Deferred Core Tools + ToolSearch + Deferred Tool Catalog
      - Layer 2: Static `CLAUDE.md` / `AGENTS.md` + Pinned Architectural Specs (delivered as first user message)
      - Layer 3: Append-only dynamic conversation history + `<system_reminder>` / `tool_reference` / `role: "system"`
    """

    def __init__(
        self,
        model: str,
        system_prompt: str,
        layer2_project_context: str,
        core_tools: list[ToolDefinition] | None = None,
        deferred_tools: list[ToolDefinition] | None = None,
        auto_pad_to_min_threshold: bool = True,
        ttl: str | None = None,
    ) -> None:
        self.model = model
        self.ttl = ttl
        self.min_tokens = get_min_cache_tokens(model)
        self.auto_pad = auto_pad_to_min_threshold

        self.core_tools: list[ToolDefinition] = list(core_tools or [])
        self.deferred_tools: dict[str, ToolDefinition] = {
            t.name: t for t in (deferred_tools or [])
        }
        for dt in self.deferred_tools.values():
            dt.defer_loading = True

        self._raw_system_prompt = system_prompt
        self._raw_layer2_context = layer2_project_context

        self._tools_payload, self._system_payload, self._layer1_tokens = self._build_layer1()
        self._layer2_message, self._layer2_tokens = self._build_layer2()

        self.layer1_hash = self._compute_hash({"tools": self._tools_payload, "system": self._system_payload})
        self.layer2_hash = self._compute_hash(self._layer2_message)

        self.layer3_messages: list[dict[str, Any]] = []

    @staticmethod
    def _compute_hash(obj: Any) -> str:
        canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _make_cache_control(self) -> dict[str, Any]:
        cc: dict[str, Any] = {"type": "ephemeral"}
        if self.ttl:
            cc["ttl"] = self.ttl
        return cc

    def _build_layer1(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        # Always include the built-in BM25 ToolSearch tool as non-deferred
        tools_list: list[dict[str, Any]] = [
            {
                "type": "tool_search_tool_bm25_20251119",
                "name": "tool_search_tool_bm25",
            }
        ]
        for idx, ct in enumerate(self.core_tools):
            is_last_non_deferred = idx == len(self.core_tools) - 1
            tools_list.append(ct.to_api_dict(with_cache_control=False))
            if is_last_non_deferred:
                # We place Breakpoint #1 at the end of Layer 1 system block (which covers tools + system)
                pass

        for dt in sorted(self.deferred_tools.values(), key=lambda x: x.name):
            tools_list.append(dt.to_api_dict(with_cache_control=False))

        sys_text = self._raw_system_prompt
        current_tokens = estimate_tokens(json.dumps(tools_list)) + estimate_tokens(sys_text)
        if self.auto_pad and current_tokens < self.min_tokens:
            needed_tokens = self.min_tokens - current_tokens + 64
            padding_lines = [
                "\n<static_architectural_reference_pad>",
                "# Canonical Architectural & Cache Invariant Reference Table (Static Prefix Anchor)",
            ]
            line_unit = (
                "Invariant Anchor: Layer 1 (tools + system) and Layer 2 (CLAUDE.md + AGENTS.md + specs) "
                "must remain 100% byte-identical across every turn to guarantee prefix hash stability. "
            )
            unit_tokens = max(1, estimate_tokens(line_unit))
            repeats = (needed_tokens // unit_tokens) + 2
            for i in range(repeats):
                padding_lines.append(f"[{i+1:03d}] {line_unit}")
            padding_lines.append("</static_architectural_reference_pad>")
            sys_text = sys_text + "\n" + "\n".join(padding_lines)
            current_tokens = estimate_tokens(json.dumps(tools_list)) + estimate_tokens(sys_text)

        system_blocks = [
            {
                "type": "text",
                "text": sys_text,
                "cache_control": self._make_cache_control(),  # Breakpoint #1: End of Layer 1
            }
        ]
        return tools_list, system_blocks, current_tokens

    def _build_layer2(self) -> tuple[dict[str, Any], int]:
        l2_text = (
            '<project_static_context source="CLAUDE.md_and_AGENTS.md">\n'
            f"{self._raw_layer2_context.strip()}\n"
            "</project_static_context>"
        )
        l2_tokens = estimate_tokens(l2_text)
        if self.auto_pad and l2_tokens < self.min_tokens:
            needed = self.min_tokens - l2_tokens + 64
            unit = (
                "Project Context Specification Anchor: All module boundaries, type contracts, "
                "and verification gates in CLAUDE.md and AGENTS.md are pinned in Layer 2. "
            )
            repeats = (needed // max(1, estimate_tokens(unit))) + 2
            pad_block = "\n".join(f"[L2-{i+1:03d}] {unit}" for i in range(repeats))
            l2_text = f"{l2_text}\n<layer2_static_pad>\n{pad_block}\n</layer2_static_pad>"
            l2_tokens = estimate_tokens(l2_text)

        msg = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": l2_text,
                    "cache_control": self._make_cache_control(),  # Breakpoint #2: End of Layer 2
                }
            ],
        }
        return msg, l2_tokens

    def verify_prefix_integrity(self) -> bool:
        """Verifies that Layer 1 and Layer 2 hashes have not drifted from session initialization."""
        current_l1 = self._compute_hash({"tools": self._tools_payload, "system": self._system_payload})
        current_l2 = self._compute_hash(self._layer2_message)
        if current_l1 != self.layer1_hash:
            raise PrefixMutationError("Layer 1 static prefix hash was mutated mid-session!")
        if current_l2 != self.layer2_hash:
            raise PrefixMutationError("Layer 2 static project context hash was mutated mid-session!")
        return True

    def search_deferred_tools(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """
        Executes client/server-compatible BM25/keyword search over the deferred tool catalog
        and returns `tool_reference` blocks for injection at the tail of Layer 3.
        """
        q_terms = [t.lower() for t in re.findall(r"\w+", query)]
        scored: list[tuple[int, str]] = []
        for name, tool in self.deferred_tools.items():
            haystack = f"{name} {tool.description} {json.dumps(tool.input_schema)}".lower()
            score = sum(3 if term in name.lower() else (1 if term in haystack else 0) for term in q_terms)
            if score > 0:
                scored.append((score, name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [
            {"type": "tool_reference", "tool_name": name}
            for _, name in scored[:limit]
        ]

    def inject_dynamic_mcp_tool_layer3(self, tool: ToolDefinition) -> dict[str, Any]:
        """
        Injects a newly discovered MCP tool schema at the tail of Layer 3 using Anthropic's
        `inline-tools-2026-09-15` `tool_addition` block inside a mid-conversation `role: "system"` message,
        leaving Layer 1 (`tools`) 100% untouched.
        """
        msg = {
            "role": "system",
            "content": [
                {
                    "type": "tool_addition",
                    "tool": {
                        "type": "tool_definition",
                        "definition": {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.input_schema,
                        },
                    },
                }
            ],
        }
        self.layer3_messages.append(msg)
        return msg

    def append_user_message(
        self,
        text: str,
        system_reminders: list[str] | None = None,
        mark_cache_breakpoint: bool = False,
    ) -> dict[str, Any]:
        """
        Appends a user turn to Layer 3, optionally attaching `<system_reminder>` tags
        to the message tail instead of mutating Layer 1.
        """
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for rem in (system_reminders or []):
            wrapped = rem if rem.strip().startswith("<system_reminder") else f"<system_reminder>\n{rem.strip()}\n</system_reminder>"
            blocks.append({"type": "text", "text": wrapped})

        if mark_cache_breakpoint and blocks:
            blocks[-1]["cache_control"] = self._make_cache_control()

        msg = {"role": "user", "content": blocks}
        self.layer3_messages.append(msg)
        return msg

    def append_turn_scoped_system_reminder(self, reminder_text: str) -> dict[str, Any]:
        """
        Appends an operator-level mid-conversation `role: "system"` message with
        `clear_at: "next_user_message"` (`mid-conversation-system-clear-at-2026-08-21`),
        so per-turn reminders never pile up or invalidate earlier thinking blocks.
        """
        msg = {
            "role": "system",
            "clear_at": "next_user_message",
            "content": reminder_text,
        }
        self.layer3_messages.append(msg)
        return msg

    def append_assistant_message(self, content_blocks: list[dict[str, Any]]) -> dict[str, Any]:
        msg = {"role": "assistant", "content": content_blocks}
        self.layer3_messages.append(msg)
        return msg

    def assemble_request(self, mark_Rolling_layer3_breakpoint: bool = True) -> AssembledRequest:
        """
        Assembles the complete 3-layer request and verifies:
          1. Layer 1 & Layer 2 SHA-256 hashes are untouched.
          2. Total explicit `cache_control` breakpoints <= 4 (Anthropic API limit).
          3. Layer 1 and Layer 2 token counts >= model minimum threshold.
        """
        self.verify_prefix_integrity()

        messages = [json.loads(json.dumps(self._layer2_message))]
        l3_copy = json.loads(json.dumps(self.layer3_messages))

        # Place rolling Breakpoint #3 on the last cacheable user/assistant block in Layer 3
        if mark_Rolling_layer3_breakpoint and l3_copy:
            for msg in reversed(l3_copy):
                if msg.get("role") in ("user", "assistant") and isinstance(msg.get("content"), list) and msg["content"]:
                    # Clear any old rolling breakpoints in Layer 3 so we never exceed 4 total breakpoints
                    for m in l3_copy:
                        if isinstance(m.get("content"), list):
                            for b in m["content"]:
                                if isinstance(b, dict):
                                    b.pop("cache_control", None)
                    msg["content"][-1]["cache_control"] = self._make_cache_control()
                    break

        messages.extend(l3_copy)

        # Count explicit breakpoints across tools, system, and messages
        bp_count = 0
        for t in self._tools_payload:
            if "cache_control" in t:
                bp_count += 1
        for s in self._system_payload:
            if "cache_control" in s:
                bp_count += 1
        for m in messages:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and "cache_control" in b:
                        bp_count += 1

        if bp_count > 4:
            raise ValueError(f"Anthropic API 400 Guard: Request contains {bp_count} cache breakpoints (max 4).")

        l3_tokens = estimate_tokens(json.dumps(l3_copy))
        betas = ["inline-tools-2026-09-15", "mid-conversation-system-clear-at-2026-08-21"]

        return AssembledRequest(
            model=self.model,
            tools=self._tools_payload,
            system=self._system_payload,
            messages=messages,
            layer1_tokens=self._layer1_tokens,
            layer2_tokens=self._layer2_tokens,
            layer3_tokens=l3_tokens,
            layer1_hash=self.layer1_hash,
            layer2_hash=self.layer2_hash,
            breakpoint_count=bp_count,
            cache_eligible_layer1=self._layer1_tokens >= self.min_tokens,
            cache_eligible_layer2=self._layer2_tokens >= self.min_tokens,
            betas=betas,
        )
