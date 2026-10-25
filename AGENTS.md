# `AGENTS.md` — Multi-Agent Fleet & `@heretek-ai/pi-configs` Interoperability Charter

`cod.ai` natively loads specialist charters from `@heretek-ai/pi-configs` (`pi_configs_upstream/agents/<slug>/AGENTS.md`) and switches charters via Layer 3 mid-conversation `role: "system"` / `<system_reminder>` blocks so the Layer 1 and Layer 2 ephemeral prompt caches remain 100% intact.

## Built-In Core Sub-Agents
- **Lead `/goal` Coordinator (`src/agents/coordinator.py`)**: Decomposes specs into isolated `git worktree` branches and synthesizes results via `StructuredMemoryStore`.
- **Read-Only `Explore` Sub-Agent (`src/agents/explore_agent.py`)**: Auto-triggered on $>3$ `Glob`/`Grep` queries; returns a distilled 1,000–2,000 token architectural brief.
- **Two-Tier `Compact Service` (`src/agents/compaction.py`)**: Enforces `NO_TOOLS_PREAMBLE`, strips `<analysis>`, validates the 9-section `<summary>`, and restores the 5 most recently accessed files.
- **Adversarial Verification Agent (`src/agents/verifier.py`)**: Read-only on project files (exit code `2` guard), ephemeral harnesses in `/tmp` only, executes the 5-step Universal Baseline, and forces the Lead Agent to spot-check 2–3 commands.
