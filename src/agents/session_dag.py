"""
Pi-Compatible JSONL Session Tree DAG & Cache Re-billed Meter (`/src/agents/session_dag.py`).
Directly implements the two flagship innovations from `earendil-works/pi` (`Inside the Pi Harness`):
  1. Sessions are Trees, Not Lists (`session.jsonl`):
     - Every turn entry has `id` and `parentId`.
     - `/tree` moves the active leaf pointer anywhere in the file without deleting history.
     - Branching from an earlier node preserves 100% of the cached prefix up to the branch point.
     - Compactions attach a materialized `retainedTail` checkpoint node.
  2. The "Cache Re-billed" Meter:
     - Tracks cumulative `cache_read_input_tokens`, `cache_creation_input_tokens`, and uncached `input_tokens`.
     - Computes exact dollar cost re-billed due to cache misses (`model_switch`, `ttl_expired_idle`, `prefix_mutation`)
       while excluding intentional compactions from miss counts.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
import uuid
from typing import Any


@dataclass
class SessionTreeNode:
    id: str
    parentId: str | None
    role: str
    content: Any
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    retainedTail: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "parentId": self.parentId,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
        if self.retainedTail is not None:
            d["retainedTail"] = self.retainedTail
        return d


@dataclass
class CacheMeterSummary:
    cumulative_cache_reads: int = 0
    cumulative_cache_writes: int = 0
    cumulative_uncached_input: int = 0
    rebilled_tokens: int = 0
    rebilled_cost_usd: float = 0.0
    cache_misses: int = 0
    miss_reasons: list[str] = field(default_factory=list)

    def format_pi_footer(self) -> str:
        total_eligible = self.cumulative_cache_reads + self.cumulative_cache_writes + self.cumulative_uncached_input
        hit_rate = (self.cumulative_cache_reads / total_eligible * 100.0) if total_eligible > 0 else 0.0
        return (
            f"Cache Hit Rate: {hit_rate:.1f}% | "
            f"Reads: {self.cumulative_cache_reads:,} tok | Writes: {self.cumulative_cache_writes:,} tok | "
            f"Cache Re-billed: ${self.rebilled_cost_usd:.4f} ({self.rebilled_tokens:,} tokens, {self.cache_misses} misses)"
        )


class PiSessionDAG:
    """
    Append-only JSONL DAG session store compatible with Pi's `session.jsonl` specification.
    """

    def __init__(self, jsonl_path: str | Path) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.nodes: dict[str, SessionTreeNode] = {}
        self.active_leaf_id: str | None = None
        self.meter = CacheMeterSummary()
        if self.jsonl_path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            node = SessionTreeNode(
                id=raw["id"],
                parentId=raw.get("parentId"),
                role=raw["role"],
                content=raw["content"],
                timestamp=raw.get("timestamp", time.time()),
                metadata=raw.get("metadata", {}),
                retainedTail=raw.get("retainedTail"),
            )
            self.nodes[node.id] = node
            self.active_leaf_id = node.id

    def append_node(
        self,
        role: str,
        content: Any,
        parent_id: str | None = "AUTO_LEAF",
        metadata: dict[str, Any] | None = None,
        retained_tail: list[dict[str, Any]] | None = None,
        node_id: str | None = None,
    ) -> SessionTreeNode:
        resolved_parent = self.active_leaf_id if parent_id == "AUTO_LEAF" else parent_id
        if resolved_parent is not None and resolved_parent not in self.nodes:
            raise KeyError(f"Parent node '{resolved_parent}' does not exist in session DAG.")

        nid = node_id or f"e{len(self.nodes) + 1}_{uuid.uuid4().hex[:6]}"
        node = SessionTreeNode(
            id=nid,
            parentId=resolved_parent,
            role=role,
            content=content,
            metadata=metadata or {},
            retainedTail=retained_tail,
        )
        self.nodes[nid] = node
        self.active_leaf_id = nid
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(node.to_dict(), ensure_ascii=False) + "\n")
        return node

    def move_leaf_pointer(self, target_node_id: str) -> list[SessionTreeNode]:
        """
        Implements Pi's `/tree` command: moves `active_leaf_id` to any existing node in the tree
        without deleting or mutating `session.jsonl`.
        """
        if target_node_id not in self.nodes:
            raise KeyError(f"Target node '{target_node_id}' not found in session DAG.")
        self.active_leaf_id = target_node_id
        return self.get_active_path()

    def get_active_path(self, leaf_id: str | None = None) -> list[SessionTreeNode]:
        """Returns the ordered root-to-leaf path for the active leaf."""
        curr_id = leaf_id if leaf_id is not None else self.active_leaf_id
        path: list[SessionTreeNode] = []
        visited: set[str] = set()
        while curr_id is not None:
            if curr_id in visited:
                raise RuntimeError(f"Cycle detected in session DAG at node {curr_id}")
            visited.add(curr_id)
            node = self.nodes[curr_id]
            path.append(node)
            curr_id = node.parentId
        path.reverse()
        return path

    def record_turn_usage(
        self,
        cache_read_tokens: int,
        cache_write_tokens: int,
        uncached_input_tokens: int,
        expected_cached_prefix_tokens: int = 0,
        cause: str | None = None,
        is_intentional_compaction: bool = False,
        base_input_price_per_mtok: float = 4.0,
        cache_write_multiplier: float = 1.25,
        cache_read_multiplier: float = 0.05,
    ) -> CacheMeterSummary:
        """
        Updates the Pi Cache Meter. If `expected_cached_prefix_tokens > 0` but `cache_read_tokens < expected_cached_prefix_tokens`
        (and `is_intentional_compaction` is False), attributes the re-billed tokens and dollar cost.
        """
        self.meter.cumulative_cache_reads += cache_read_tokens
        self.meter.cumulative_cache_writes += cache_write_tokens
        self.meter.cumulative_uncached_input += uncached_input_tokens

        if not is_intentional_compaction and expected_cached_prefix_tokens > cache_read_tokens:
            missed_tokens = expected_cached_prefix_tokens - cache_read_tokens
            # Re-billed penalty is the difference between paying a fresh cache write (1.25x) vs a cache read (0.05x)
            diff_rate_per_mtok = base_input_price_per_mtok * (cache_write_multiplier - cache_read_multiplier)
            cost_usd = (missed_tokens / 1_000_000.0) * diff_rate_per_mtok
            self.meter.rebilled_tokens += missed_tokens
            self.meter.rebilled_cost_usd = round(self.meter.rebilled_cost_usd + cost_usd, 6)
            self.meter.cache_misses += 1
            reason = cause or "cache miss after prefix invalidation or TTL expiry"
            self.meter.miss_reasons.append(f"{reason} ({missed_tokens:,} tok, ${cost_usd:.4f})")

        return self.meter
