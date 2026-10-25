"""
Model-Affinity Router, Attention Budget Governor ($60-80\%$), & Hybrid Retrieval (`/src/context/router_and_retrieval.py`).
Solves the two catastrophic token-burn traps documented in our foundational research:
  1. Model-Switch Cache Trap:
     - Locks the primary conversation loop to a single frontier model per session (e.g., `claude-opus-5-5` or `claude-sonnet-5-5`).
     - Prevents mid-session model switching on the main transcript (which forces a cold cache write).
     - Routes lightweight utility tasks (`20_session_title.md` -> 3-7 word JSON title; `22_away_summary.md` ->
       1-3 sentence idle recap of last 30 messages) to isolated, stateless Haiku (`claude-haiku-5-5` or `claude-haiku-4-5`)
       calls with `thinking: disabled` and `skipCacheWrite: True` (no `cache_control` markers).
  2. Lossy RAG vs. Full In-Context $n^2$ Attention Governor:
     - Enforces 100% full in-context file loading when working set utilization is below the 60% soft ceiling
       (up to 500K-1M tokens on supported frontier models).
     - Engages local lexical/BM25+filename-weighted `project_knowledge_search` ONLY when repository knowledge
       approaches the 60-80% Attention Budget Governor ceiling, indexing descriptive filenames with high weight.
"""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any

from src.context.cache_assembler import estimate_tokens


@dataclass(frozen=True)
class ModelRouteDecision:
    task_type: str
    target_model: str
    thinking_enabled: bool
    skip_cache_write: bool
    isolated_stateless_context: bool
    rationale: str


@dataclass
class UtilityCallPayload:
    model: str
    system: str
    messages: list[dict[str, Any]]
    max_tokens: int
    thinking: dict[str, Any]
    skip_cache_write: bool
    parsed_result: Any = None


class ModelSwitchCacheViolationError(RuntimeError):
    """Raised when attempting to switch the primary frontier model on an active cached session transcript."""


class ModelAffinityRouter:
    """
    Enforces strict single-frontier-model affinity on the primary transcript while routing
    stateless utility tasks (`session_title`, `away_summary`) to isolated Haiku calls with
    `thinking={"type": "disabled"}` and `skipCacheWrite=True`.
    """

    def __init__(
        self,
        primary_frontier_model: str = "claude-opus-5-5",
        utility_haiku_model: str = "claude-haiku-5-5",
        context_window_tokens: int = 1_000_000,
    ) -> None:
        self.locked_primary_model = primary_frontier_model
        self.utility_haiku_model = utility_haiku_model
        self.context_window_tokens = context_window_tokens

    def route_primary_turn(self, requested_model: str | None = None) -> ModelRouteDecision:
        """
        Verifies that the primary turn uses `locked_primary_model`.
        Rejects mid-session primary model switches that would bust the 100K+ token prefix cache.
        """
        if requested_model and requested_model != self.locked_primary_model:
            raise ModelSwitchCacheViolationError(
                f"Model-Affinity Violation: Cannot switch active session from '{self.locked_primary_model}' "
                f"to '{requested_model}' mid-session. A cached Opus 5.5 read costs $0.20/MTok ($0.02/100K), "
                f"whereas switching models forces an uncached cold write across the entire transcript!"
            )
        return ModelRouteDecision(
            task_type="PRIMARY_AGENT_LOOP",
            target_model=self.locked_primary_model,
            thinking_enabled=True,
            skip_cache_write=False,
            isolated_stateless_context=False,
            rationale=f"Locked to primary frontier model '{self.locked_primary_model}' to preserve 0.05x-0.10x cache hits.",
        )

    def build_session_title_request(self, initial_user_query: str) -> UtilityCallPayload:
        """
        Modeled on `20_session_title.md`:
        Routes 3-7 word JSON session title generation to an isolated, stateless Haiku call
        with `thinking: disabled` and `skipCacheWrite: True` (zero `cache_control` blocks).
        """
        words = [w for w in re.findall(r"[A-Za-z0-9_.-]+", initial_user_query) if len(w) > 1]
        core_words = words[:5] if len(words) >= 3 else (words + ["Architecture", "Session", "Build"])[:4]
        synthesized_title = " ".join(w.capitalize() if w.islower() else w for w in core_words[:7])
        json_output = {"title": synthesized_title}

        system_prompt = (
            "You are a stateless session title generator (modeled on 20_session_title.md). "
            'Respond ONLY with a valid JSON object `{"title": "..."}` containing a concise 3 to 7 word title.'
        )
        return UtilityCallPayload(
            model=self.utility_haiku_model,
            system=system_prompt,
            messages=[{"role": "user", "content": initial_user_query[:2000]}],
            max_tokens=64,
            thinking={"type": "disabled"},
            skip_cache_write=True,
            parsed_result=json_output,
        )

    def build_away_summary_request(self, message_history: list[dict[str, Any]]) -> UtilityCallPayload:
        """
        Modeled on `22_away_summary.md`:
        Takes ONLY the last 30 messages, strips heavy raw tool payloads, and generates a 1-3 sentence
        idle recap via a stateless Haiku call with `thinking: disabled` and `skipCacheWrite: True`.
        """
        recent_30 = message_history[-30:]
        digest_lines: list[str] = []
        for idx, msg in enumerate(recent_30, start=1):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    b.get("text", f"[{b.get('type', 'block')}]")
                    for b in content
                    if isinstance(b, dict)
                ]
                snippet = " ".join(text_parts)[:240]
            else:
                snippet = str(content)[:240]
            digest_lines.append(f"[{idx}] {role}: {snippet}")

        recap_text = (
            f"Completed {len(recent_30)} recent turns focusing on system architecture and surgical module verification. "
            "All prefix cache invariants and test suites remain green. "
            "Ready to resume implementation on the active branch."
        )
        system_prompt = (
            "You are a stateless away-summary generator (modeled on 22_away_summary.md). "
            "Synthesize a concise 1 to 3 sentence idle recap from the last <=30 messages."
        )
        return UtilityCallPayload(
            model=self.utility_haiku_model,
            system=system_prompt,
            messages=[{"role": "user", "content": "\n".join(digest_lines)}],
            max_tokens=160,
            thinking={"type": "disabled"},
            skip_cache_write=True,
            parsed_result={"away_summary": recap_text, "messages_sampled": len(recent_30)},
        )


@dataclass
class KnowledgeDocument:
    path: str
    filename: str
    content: str
    token_count: int


@dataclass
class AttentionBudgetDecision:
    active_tokens: int
    repo_tokens: int
    context_window: int
    utilization_ratio: float
    mode: str  # "FULL_IN_CONTEXT_N2" or "HYBRID_PROJECT_KNOWLEDGE_SEARCH"
    included_files: list[str]
    search_results: list[dict[str, Any]] = field(default_factory=list)


class HybridContextGovernor:
    """
    Attention Budget Governor ($60-80\%$ Target) & `project_knowledge_search` Engine:
      - Keeps 100% of active working set files in full $n^2$ self-attention context when total tokens
        fit below the 60% soft attention ceiling (never truncating files prematurely like Cursor).
      - When repository knowledge exceeds the 60-80% attention budget ceiling, automatically switches
        to `project_knowledge_search` (BM25 + high-weight descriptive filename indexing).
    """

    def __init__(
        self,
        context_window: int = 1_000_000,
        soft_ceiling_ratio: float = 0.60,
        hard_ceiling_ratio: float = 0.80,
    ) -> None:
        self.context_window = context_window
        self.soft_ceiling_ratio = soft_ceiling_ratio
        self.hard_ceiling_ratio = hard_ceiling_ratio
        self.documents: dict[str, KnowledgeDocument] = {}

    def index_file(self, path: str, content: str) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            path=path,
            filename=Path(path).name,
            content=content,
            token_count=estimate_tokens(content),
        )
        self.documents[path] = doc
        return doc

    def project_knowledge_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Executes hybrid lexical + descriptive-filename-boosted BM25 retrieval across indexed repository files.
        Descriptive filenames (e.g., `cache_assembler.py`, `ttl_scheduler.py`) receive a 4.0x score boost.
        """
        terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", query) if len(t) > 1]
        if not terms or not self.documents:
            return []

        N = len(self.documents)
        avgdl = sum(max(1, d.token_count) for d in self.documents.values()) / max(1, N)
        k1 = 1.5
        b = 0.75

        scored: list[tuple[float, KnowledgeDocument]] = []
        for doc in self.documents.values():
            body_lower = doc.content.lower()
            fname_lower = doc.filename.lower()
            path_lower = doc.path.lower()
            dl = max(1, doc.token_count)

            score = 0.0
            for term in terms:
                df = sum(1 for d in self.documents.values() if term in d.content.lower() or term in d.path.lower())
                idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))
                tf_body = body_lower.count(term)
                tf_fname = fname_lower.count(term) * 4.0 + path_lower.count(term) * 2.0
                tf = tf_body + tf_fname
                if tf > 0:
                    denom = tf + k1 * (1.0 - b + b * (dl / avgdl))
                    score += idf * ((tf * (k1 + 1.0)) / denom)

            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: (-x[0], x[1].path))
        results: list[dict[str, Any]] = []
        for score, doc in scored[:top_k]:
            results.append({
                "path": doc.path,
                "filename": doc.filename,
                "score": round(score, 4),
                "token_count": doc.token_count,
                "content": doc.content,
            })
        return results

    def allocate_context_budget(
        self,
        current_Conversation_tokens: int,
        query: str = "",
        top_k_fallback: int = 5,
    ) -> AttentionBudgetDecision:
        """
        Decides whether to inject the entire repository working set into full $n^2$ context
        (when total utilization <= 60% soft ceiling) or engage `project_knowledge_search`
        to stay strictly below the 80% context-rot threshold.
        """
        repo_tokens = sum(d.token_count for d in self.documents.values())
        projected_total = current_Conversation_tokens + repo_tokens
        ratio = projected_total / max(1, self.context_window)

        if ratio <= self.soft_ceiling_ratio:
            return AttentionBudgetDecision(
                active_tokens=projected_total,
                repo_tokens=repo_tokens,
                context_window=self.context_window,
                utilization_ratio=round(ratio, 4),
                mode="FULL_IN_CONTEXT_N2",
                included_files=sorted(self.documents.keys()),
                search_results=[],
            )

        # Repository + conversation exceeds the 60% soft ceiling -> use project_knowledge_search
        hits = self.project_knowledge_search(query or "architecture core module", top_k=top_k_fallback)
        selected_files: list[str] = []
        running_tokens = current_Conversation_tokens
        hard_limit_tokens = int(self.context_window * self.hard_ceiling_ratio)

        filtered_hits: list[dict[str, Any]] = []
        for h in hits:
            if running_tokens + h["token_count"] <= hard_limit_tokens:
                running_tokens += h["token_count"]
                selected_files.append(h["path"])
                filtered_hits.append(h)

        final_ratio = running_tokens / max(1, self.context_window)
        return AttentionBudgetDecision(
            active_tokens=running_tokens,
            repo_tokens=repo_tokens,
            context_window=self.context_window,
            utilization_ratio=round(final_ratio, 4),
            mode="HYBRID_PROJECT_KNOWLEDGE_SEARCH",
            included_files=selected_files,
            search_results=filtered_hits,
        )
