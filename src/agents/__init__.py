"""Phase 4: Multi-Agent Fleet, Compaction Service, & Adversarial Verifier."""
from src.agents.compaction import (
    MANDATORY_9_SECTIONS,
    NO_TOOLS_PREAMBLE,
    CompactServiceResult,
    CompactionValidationError,
    MicroCompactionResult,
    TwoTierCompactionEngine,
)
from src.agents.coordinator import (
    GoalSubTask,
    GoalSynthesisReport,
    GoalWorktreeCoordinator,
    WorktreeTaskResult,
)
from src.agents.explore_agent import (
    DiscoveryQuery,
    ExploreArchitecturalBrief,
    ReadOnlyExploreSubAgent,
    ReadOnlyViolationError,
)
from src.agents.memory import (
    MemoryConcurrencyError,
    MemoryFileState,
    MemoryMatchError,
    StructuredMemoryStore,
)
from src.agents.session_dag import (
    CacheMeterSummary,
    PiSessionDAG,
    SessionTreeNode,
)
from src.agents.verifier import (
    ANTI_RATIONALIZATION_DIRECTIVES,
    AdversarialVerificationAgent,
    BaselineStepResult,
    LeadAgentSpotCheckReport,
    VerificationReport,
    VerifierPermissionError,
)

__all__ = [
    "ANTI_RATIONALIZATION_DIRECTIVES",
    "AdversarialVerificationAgent",
    "BaselineStepResult",
    "CacheMeterSummary",
    "CompactServiceResult",
    "CompactionValidationError",
    "DiscoveryQuery",
    "ExploreArchitecturalBrief",
    "GoalSubTask",
    "GoalSynthesisReport",
    "GoalWorktreeCoordinator",
    "LeadAgentSpotCheckReport",
    "MANDATORY_9_SECTIONS",
    "MemoryConcurrencyError",
    "MemoryFileState",
    "MemoryMatchError",
    "MicroCompactionResult",
    "NO_TOOLS_PREAMBLE",
    "PiSessionDAG",
    "ReadOnlyExploreSubAgent",
    "ReadOnlyViolationError",
    "SessionTreeNode",
    "StructuredMemoryStore",
    "TwoTierCompactionEngine",
    "VerificationReport",
    "VerifierPermissionError",
    "WorktreeTaskResult",
]
