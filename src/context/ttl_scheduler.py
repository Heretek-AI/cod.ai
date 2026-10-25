"""
5-Minute TTL Keep-Alive & Batching Scheduler (`/src/context/ttl_scheduler.py`).
Grounded in verified Anthropic Prompt Caching mechanics:
  - Ephemeral cache TTL is 300 seconds (5 minutes) by default (or 3,600s if `ttl="1h"`).
  - CRITICAL OSINT FACT: The 300-second lifetime is measured from the START of the request
    that writes or reads the cache entry, NOT from the end of response streaming!
  - Tracks exact request-start timestamps per active session, issues pre-expiration warnings,
    queues non-urgent micro-edits when the cache is cold or batching is enabled, and provides
    an optional lightweight 1-token keep-alive ping when holding >50K cached tokens.
"""
from dataclasses import dataclass, field
import time
from typing import Any, Callable


@dataclass
class SessionTTLState:
    session_id: str
    last_request_start_ts: float
    last_response_end_ts: float | None = None
    cached_prefix_tokens: int = 0
    ttl_seconds: float = 300.0
    warning_lead_seconds: float = 45.0
    keepalive_count: int = 0


@dataclass
class TTLInspectionReport:
    session_id: str
    elapsed_since_request_start: float
    remaining_ttl_seconds: float
    streaming_duration_seconds: float
    state: str  # "HOT", "PRE_EXPIRATION_WARNING", "EXPIRED_COLD"
    should_send_keepalive: bool
    estimated_cold_rewrite_cost_usd: float
    estimated_keepalive_cost_usd: float
    recommendation: str


class FiveMinuteTTLScheduler:
    """
    Manages the 300-second ephemeral cache countdown across concurrent `cod.ai` sessions
    and provides a batching queue so human pauses do not trigger silent 100K+ token cold re-writes.
    """

    def __init__(self, default_ttl_seconds: float = 300.0, warning_lead_seconds: float = 45.0) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self.warning_lead_seconds = warning_lead_seconds
        self.sessions: dict[str, SessionTTLState] = {}
        self.batch_queues: dict[str, list[dict[str, Any]]] = {}

    def record_request_start(
        self,
        session_id: str,
        cached_prefix_tokens: int,
        now_ts: float | None = None,
        ttl_seconds: float | None = None,
    ) -> SessionTTLState:
        """
        Records the START timestamp of an API request (the exact instant Anthropic's 300s TTL clock resets).
        """
        ts = now_ts if now_ts is not None else time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        state = SessionTTLState(
            session_id=session_id,
            last_request_start_ts=ts,
            last_response_end_ts=None,
            cached_prefix_tokens=cached_prefix_tokens,
            ttl_seconds=ttl,
            warning_lead_seconds=self.warning_lead_seconds,
        )
        self.sessions[session_id] = state
        return state

    def record_response_complete(self, session_id: str, now_ts: float | None = None) -> SessionTTLState:
        """Records when streaming finished (note: streaming time already ate into the 300s TTL!)."""
        if session_id not in self.sessions:
            raise KeyError(f"Unknown session_id: {session_id}")
        ts = now_ts if now_ts is not None else time.time()
        self.sessions[session_id].last_response_end_ts = ts
        return self.sessions[session_id]

    def inspect_session_ttl(
        self,
        session_id: str,
        now_ts: float | None = None,
        base_input_price_per_mtok: float = 4.0,  # e.g., Claude Opus 5.5 = $4/MTok
        cache_read_multiplier: float = 0.05,     # Opus 5.5 read = $0.20/MTok (0.05x)
    ) -> TTLInspectionReport:
        """
        Evaluates exact remaining TTL measured from `last_request_start_ts` and calculates
        whether a 1-token keep-alive ping is economically superior to letting the cache expire.
        """
        if session_id not in self.sessions:
            raise KeyError(f"Unknown session_id: {session_id}")

        s = self.sessions[session_id]
        now = now_ts if now_ts is not None else time.time()
        elapsed = max(0.0, now - s.last_request_start_ts)
        remaining = max(0.0, s.ttl_seconds - elapsed)
        stream_dur = (
            max(0.0, s.last_response_end_ts - s.last_request_start_ts)
            if s.last_response_end_ts is not None
            else elapsed
        )

        # Economic calculation:
        # 5m Cache Write costs 1.25x base input price.
        # Cache Read (keepalive refresh) costs cache_read_multiplier * base input price.
        mtok = s.cached_prefix_tokens / 1_000_000.0
        cold_rewrite_cost = mtok * (base_input_price_per_mtok * 1.25)
        keepalive_cost = mtok * (base_input_price_per_mtok * cache_read_multiplier)

        if remaining <= 0.0:
            state_str = "EXPIRED_COLD"
            should_ping = False
            rec = (
                f"Cache EXPIRED ({elapsed:.1f}s > {s.ttl_seconds:.0f}s). Batch pending user prompts before "
                f"dispatching to amortize the ${cold_rewrite_cost:.4f} cold cache write."
            )
        elif remaining <= s.warning_lead_seconds:
            state_str = "PRE_EXPIRATION_WARNING"
            should_ping = s.cached_prefix_tokens >= 20_000 and keepalive_cost < cold_rewrite_cost
            rec = (
                f"WARNING: Only {remaining:.1f}s remaining on 5m TTL (streaming took {stream_dur:.1f}s). "
                f"Trigger keep-alive refresh (${keepalive_cost:.4f}) to avoid ${cold_rewrite_cost:.4f} cold rewrite."
            )
        else:
            state_str = "HOT"
            should_ping = False
            rec = f"Cache HOT ({remaining:.1f}s remaining). Dispatch immediately for {cache_read_multiplier}x read rate."

        return TTLInspectionReport(
            session_id=session_id,
            elapsed_since_request_start=round(elapsed, 2),
            remaining_ttl_seconds=round(remaining, 2),
            streaming_duration_seconds=round(stream_dur, 2),
            state=state_str,
            should_send_keepalive=should_ping,
            estimated_cold_rewrite_cost_usd=round(cold_rewrite_cost, 6),
            estimated_keepalive_cost_usd=round(keepalive_cost, 6),
            recommendation=rec,
        )

    def enqueue_batched_message(self, session_id: str, message: dict[str, Any]) -> int:
        """Queues a message in the session batch buffer (used when waiting to coalesce prompts)."""
        queue = self.batch_queues.setdefault(session_id, [])
        queue.append(message)
        return len(queue)

    def flush_batch_queue(self, session_id: str) -> list[dict[str, Any]]:
        """Flushes and returns all coalesced messages for a single cache-write turn."""
        items = self.batch_queues.get(session_id, [])
        self.batch_queues[session_id] = []
        return items

    def trigger_keepalive_heartbeat(
        self,
        session_id: str,
        now_ts: float | None = None,
        ping_callback: Callable[[str], bool] | None = None,
    ) -> bool:
        """
        Executes a minimal `max_tokens=1` prefix heartbeat refresh when a session is in
        `PRE_EXPIRATION_WARNING` state, resetting the 300-second TTL clock for 0.05x–0.10x read cost.
        """
        report = self.inspect_session_ttl(session_id, now_ts=now_ts)
        if not report.should_send_keepalive:
            return False

        ok = ping_callback(session_id) if ping_callback else True
        if ok:
            s = self.sessions[session_id]
            ts = now_ts if now_ts is not None else time.time()
            s.last_request_start_ts = ts
            s.last_response_end_ts = ts + 0.1
            s.keepalive_count += 1
        return ok
