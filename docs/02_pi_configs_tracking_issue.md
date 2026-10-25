# Tracking Issue: Upgrade `@heretek-ai/pi-configs` to 100% `cod.ai` Architectural Invariant Compliance (v1.3.0)

**Target Repository:** [Heretek-AI/pi-configs](https://github.com/Heretek-AI/pi-configs) ([`@heretek-ai/pi-configs` on pi.dev](https://pi.dev/packages/@heretek-ai/pi-configs))  
**Linked Architecture Repo:** [Heretek-AI/cod.ai](https://www.google.com/search?q=https://github.com/Heretek-AI/cod.ai)  
**Proposed Labels:** `enhancement`, `architecture`, `cache-optimization`, `specialist-fleet`  
**Status:** Ready to File (`pi_configs_upstream/create_tracking_issue.sh` + drop-in PR payload generated in `pi_configs_upstream/`)

---

## 1. Problem Statement & Forensic Audit Summary

During the Phase 1 Harness Evaluation for [Heretek-AI/cod.ai](https://www.google.com/search?q=https://github.com/Heretek-AI/cod.ai) (`docs/01_harness_decision_matrix.md`), we audited [Pi (`@earendil-works/pi-coding-agent`)](https://github.com/earendil-works/pi) combined with [`@heretek-ai/pi-configs` (v1.2.0)](https://pi.dev/packages/@heretek-ai/pi-configs) against our **Six Non-Negotiable Architectural Invariants**.

While `@heretek-ai/pi-configs` natively passes Invariant #2 (Deferred Tool Loading via `pi-mcp-adapter` ~200-token proxy), Invariant #5 (Clean-Context Sub-Agent Spawning via `Pi-Agents-Team` RPC `<final_answer>` extraction), and Invariant #6 (Headless CLI/RPC execution), **three areas scored `PARTIAL` due to extension-level behavior that we can fix directly in `Heretek-AI/pi-configs`**:

1. **Invariant #1 (`PARTIAL` on `/specialist` Mode Switch) — Mid-Session Charter Mutation Busts the Prefix Cache**:
   - **Root Cause**: Currently in `src/index.ts`, running `/specialist <slug>` dynamically replaces the active session charter in the top-level system prompt (Layer 1). Per the [Anthropic Prompt Caching Specification](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) and [Inside the Pi Harness](https://rohitghumare.com/blog/inside-the-pi-harness/), mutating Layer 1 invalidates 100% of the cached prefix, forcing every subsequent message in the transcript to be re-billed at uncached rates.
   - **Fix in `Heretek-AI/pi-configs`**: Update `/specialist <slug>` in `src/index.ts` to keep the base 20-line Pi system prompt byte-identical in Layer 1 and inject the specialist's `AGENTS.md` charter at the **tail of Layer 3** using either an Anthropic mid-conversation `role: "system"` block ([Mid-Conversation System Messages](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)) or a structured `<system_reminder type="specialist_charter_switch">` block, OR fork a child DAG branch in `session.jsonl` (`parentId` anchored to the last cached turn).
2. **Invariant #3 (`PARTIAL` on Dual-Polarity Mode Switching) — Missing Mode A ("Holistic Web Architect") `<antArtifact>` Iterative Loop**:
   - **Root Cause**: While Guild 1 includes `system-architect`, its charter is oriented toward CLI linting (`spectral lint`, `codebase-memory-mcp`) rather than replicating `claude.ai` Web's zero-tool-noise $n^2$ self-attention synthesis and $>100$-line iterative drafting protocol (`Outline -> Section-by-Section Generation -> Review & Refine -> Final Output`).
   - **Fix in `Heretek-AI/pi-configs`**: Add Specialist #72 (`holistic-web-architect`) to Guild 1 with GOAL XML framing (`<context>`, `<objective>`, `<constraints>`, `<output_contract>`), curated Skills Playbooks, and a deterministic `hooks.yaml` post-generation gate that rejects placeholder comments (`// rest of code...`, `TODO: implement`) with exit code `2`.
3. **Invariant #4 (`PARTIAL` on Attention Budget Governor) — Late Compaction (~92% vs. 60–80% Target) & Missing Adversarial Verifier Specialist**:
   - **Root Cause**: Default Pi waits until `contextWindow - 16,384` tokens (~92% on 200K) before compacting, well inside the "context rot" zone documented in [Anthropic Context Windows](https://platform.claude.com/docs/en/build-with-claude/context-windows).
   - **Fix in `Heretek-AI/pi-configs`**:
     - Add Specialist #73 (`attention-budget-governor`) & extension hook that monitors Pi's token meter on every turn, enforces a **60% soft / 75% hard attention budget ceiling**, runs cache-safe Stage 1 Micro-Compaction (only pruning tool results *after* the last `cache_control` breakpoint), and triggers the 9-section `<summary>` (`21_compact_service.md` with `NO_TOOLS_PREAMBLE` and top-5 file restoration) at 75–80% with `skipCacheWrite: true`.
     - Add Specialist #74 (`adversarial-verifier`, modeled on `07_verification_agent.md`) to Guild 6 with strict `tool.before.*` exit-code-2 hooks blocking any project file writes outside `/tmp`, enforcing the 5-step Universal Baseline, and returning `VERDICT: PASS|FAIL|PARTIAL` with mandatory lead-agent spot-check commands.

---

## 2. Deliverables Included in `pi_configs_upstream/` (Ready to Commit to `Heretek-AI/pi-configs`)

| File Path in `pi_configs_upstream/` | Target Path in `Heretek-AI/pi-configs` | Purpose |
| :--- | :--- | :--- |
| `src/cod_ai_invariant_bridge.ts` | `src/cod_ai_invariant_bridge.ts` | TypeScript Pi extension module fixing `/specialist` Layer-3 charter injection, 60–80% Attention Budget Governor, and 5-minute TTL cache heartbeat warnings. |
| `agents/holistic-web-architect/AGENTS.md` | `agents/holistic-web-architect/AGENTS.md` | Specialist #72 (Mode A Holistic Web Architect) charter with GOAL XML framing and $>100$-line iterative drafting protocol. |
| `agents/holistic-web-architect/.pi/settings.json` | `agents/holistic-web-architect/.pi/settings.json` | Model tier (`claude-opus-5-5` / `claude-sonnet-5-5`, 24k thinking, zero-noise tool allowlist). |
| `agents/holistic-web-architect/.pi/hook/hooks.yaml` | `agents/holistic-web-architect/.pi/hook/hooks.yaml` | Deterministic exit-code-2 anti-truncation hook banning `// rest of code`, `...`, and `TODO` placeholders. |
| `agents/adversarial-verifier/AGENTS.md` | `agents/adversarial-verifier/AGENTS.md` | Specialist #74 (Adversarial Verification Agent modeled on `07_verification_agent.md`) with anti-rationalization directives and 5-step Universal Baseline. |
| `agents/adversarial-verifier/.pi/hook/hooks.yaml` | `agents/adversarial-verifier/.pi/hook/hooks.yaml` | Deterministic exit-code-2 pre-tool guard blocking `Edit`/`Write` outside `/tmp` and blocking sub-agent recursion. |
| `agents/attention-budget-governor/AGENTS.md` | `agents/attention-budget-governor/AGENTS.md` | Specialist #73 (`Compact Service` modeled on `21_compact_service.md`) enforcing `NO_TOOLS_PREAMBLE`, `<analysis>` stripping, and 9-section `<summary>`. |
| `create_tracking_issue.sh` | *(Helper CLI script)* | One-click script using `gh issue create --repo Heretek-AI/pi-configs` or GitHub REST API (`POST /repos/Heretek-AI/pi-configs/issues`) to publish this exact tracking issue from any host with a GitHub token. |

---

## 3. Acceptance Criteria for `Heretek-AI/pi-configs` v1.3.0

- [ ] Running `/specialist <slug>` mid-session appends a Layer 3 `role: "system"` / `<system_reminder>` charter delta without modifying Layer 1, resulting in `0` uncached prefix re-writes (`Cache Re-billed: $0.00`).
- [ ] `holistic-web-architect` executes the 4-stage iterative drafting loop (`Outline -> Section-by-Section Generation -> Review & Refine -> Final Output`) on all specs/files $>100$ lines and aborts with exit code `2` on any placeholder comment.
- [ ] `attention-budget-governor` triggers Stage 1 cache-safe micro-compaction at 60% utilization and Stage 2 9-section `<summary>` compaction (plus top-5 recently accessed files) at 75% utilization.
- [ ] `adversarial-verifier` blocks all non-`/tmp` file mutations via `hooks.yaml` (exit code `2`) and outputs `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: PARTIAL` with 2–3 reproducible spot-check commands.
