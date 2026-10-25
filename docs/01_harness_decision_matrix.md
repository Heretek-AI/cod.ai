# Phase 1: Harness Architecture Evaluation & Selection (`cod.ai`)

**Document ID:** `01_harness_decision_matrix.md`  
**Target Repository:** [Heretek-AI/cod.ai](https://github.com/Heretek-AI/cod.ai)  
**Date:** October 24, 2026  
**Status:** Architecture Decision Record (ADR-001) — Ready for Review

---

## 1. Executive Summary: Build Custom `cod.ai` Core Unifying Pi's DAG/Extension Protocol with Claude Code's 3-Layer Cache & Verification Engine

Every candidate open-source and proprietary coding harness discovered during Phase 0 was evaluated against our **Six Non-Negotiable Architectural Invariants**. **No existing standalone harness satisfies all 6 invariants out of the box without invasive patching.** However, **[Pi (`@earendil-works/pi-coding-agent`)](https://github.com/earendil-works/pi) combined with Heretek-AI's own [`@heretek-ai/pi-configs`](https://pi.dev/packages/@heretek-ai/pi-configs)** comes remarkably close—solving append-only tree transcripts (`session.jsonl`), zero-noise static system prompts, cache re-billing telemetry, and lazy ~200-token MCP proxy adapters (`pi-mcp-adapter`).

In strict compliance with our **Build-vs-Buy Mandate (Constraint #2)**, we will **build `cod.ai`'s Core Orchestration Engine from scratch** while adopting **Pi's JSONL DAG Session Tree format (`id`/`parentId`), Cache Re-billing Meter arithmetic, and `@heretek-ai/pi-configs` Specialist Charter/Hook compatibility** as first-class native primitives.

---

## 2. Evaluation Against the Six Non-Negotiable Architectural Invariants

| Architectural Invariant | **Pi (`earendil-works/pi`) + `@heretek-ai/pi-configs`** | **Claude Code CLI (`v2.1.220`)** | **OpenCode (`anomalyco/opencode`)** | **Hermes Agent (`NousResearch`)** | **Aider (`Aider-AI/aider`)** | **Cline (`cline/cline`)** | **`cod.ai` Custom Core (Proposed)** |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Byte-Identical Static Prefix Guarantee** (Layer 1 System + Layer 2 `CLAUDE.md`/`AGENTS.md` + Layer 3 Dynamic) | **PASS (Core) / PARTIAL (Mode Switch)**: 20-line static prompt with zero timestamps ([Inside the Pi Harness](https://rohitghumare.com/blog/inside-the-pi-harness/)). However, switching specialist charters via `/specialist` mutates the system prompt unless isolated in sub-processes. | **PASS**: Strict 3-layer stack; `CLAUDE.md` in Layer 2 user message; `<system-reminder>` in Layer 3 ([Inside the Claude Code Harness](https://rohitghumare.com/blog/inside-the-claude-code-harness/)). (Proprietary/Closed). | **FAIL**: Moving plan/build reminders mutates earlier message positions and busts the prompt cache ([Issue #58485](https://github.com/anomalyco/opencode/issues/58485)). | **PARTIAL**: State mutations (`hermes_state_prune_rewrite.py`) can rewrite transcript history in place. | **FAIL**: Dynamic repo-map updates and `/add` or `/drop` file edits mutate the cached prefix ([Aider Caching](https://aider.chat/docs/usage/caching.html)). | **FAIL**: Rebuilds system prompt with dynamic environment/file state on configuration changes ([Cline #8578](https://github.com/cline/cline/discussions/8578)). | **100% NATIVE PASS**: Immutable Layer 1 + Layer 2 with cryptographic SHA-256 prefix lock; mid-session updates strictly via Layer 3 `role: "system"` (`clear_at`) or `<system_reminder>`. |
| **2. Deferred Tool Schema Loading (`ToolSearch` Pattern)** | **PASS**: Native `defer_loading` + `tool_reference` support on Anthropic, plus `pi-mcp-adapter` (~200-token proxy + QuickJS `mcpScript`) in [`@heretek-ai/pi-configs`](https://pi.dev/packages/@heretek-ai/pi-configs). | **PASS**: Native `ToolSearch` (`defer_loading: true`) and `inline-tools-2026-09-15` ([Tool Search Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)). | **FAIL**: Injects enabled MCP tool schemas directly into the initial request payload. | **PARTIAL**: Supports optional MCP plugins (`optional-mcps`), but lacks native `tool_reference` expansion. | **FAIL**: Does not support MCP `ToolSearch` deferred schema loading. | **FAIL**: Injects all MCP tool schemas into the system prompt upfront ([Cline #8578](https://github.com/cline/cline/discussions/8578)). | **100% NATIVE PASS**: Dual support for Anthropic `ToolSearch` (`defer_loading: true` + `tool_reference`) AND client-side BM25/Regex `ToolSearch` + `tool_addition` for local/OpenAI endpoints. |
| **3. Dual-Polarity Mode Switching (Architect vs. Surgical Implementer)** | **PARTIAL**: Core Pi has no built-in plan/architect mode ("anti-feature"); `@heretek-ai/pi-configs` has `system-architect` and language specialists, but lacks the iterative $>100$-line `<antArtifact>` drafting loop. | **FAIL**: Hardcodes anti-overengineering rules ("no unasked helpers", "three similar lines over premature abstraction") in `01_main_system_prompt.md`. | **PARTIAL**: Has Plan vs. Build mode, but mode reminders break prompt cache ([Issue #58485](https://github.com/anomalyco/opencode/issues/58485)) and lack `claude.ai` Artifact synthesis rules. | **FAIL**: Single general-purpose agent polarity (`SOUL.md`). | **PARTIAL**: Has `/architect` + editor dual-model mode, but relies on lossy Tree-sitter repo maps rather than full-context synthesis. | **PARTIAL**: Plan/Act toggle exists, but shares a bloated tool-heavy system prompt. | **100% NATIVE PASS**: Mode A (Holistic Web Architect with zero-tool-noise $n^2$ attention, GOAL framing, Skills Playbooks, $>100$-line iterative loop) + Mode B (Surgical CLI Implementer + `COD_SIMPLE=true`). |
| **4. Attention Budget Governor ($60	ext{--}80\%$ Target)** | **PARTIAL**: Displays exact token meter and compacts within 16,384 tokens of window limit (~92% on 200K), which is above the 60–80% context-rot ceiling. | **PARTIAL**: 5-layer compaction pipeline, but exact trigger threshold is opaque and nears capacity before auto-compacting ([arXiv:2604.14228v3](https://arxiv.org/html/2604.14228v3)). | **FAIL**: Truncates or compacts late near context overflow. | **PARTIAL**: Has `hermes_state_compression.py` and holographic memory, but not governed at a strict 60–80% full-context ceiling. | **FAIL**: Aggressively compresses codebase into a tiny Tree-sitter repo map (often <10K tokens) even when 500K–1M context is available. | **FAIL**: Reactive sliding-window truncation when approaching context window limit. | **100% NATIVE PASS**: Real-time token governor enforcing full in-context $n^2$ loading up to 60% soft / 75% hard ceiling, triggering `project_knowledge_search` and Two-Tier Compaction before 80%. |
| **5. Multi-Agent Clean-Context Spawning** | **PASS (via Extension)**: Core Pi omits sub-agents, but `@heretek-ai/pi-configs` uses `Pi-Agents-Team` child-process RPC returning only `<final_answer>` blocks ([`@heretek-ai/pi-configs`](https://pi.dev/packages/@heretek-ai/pi-configs)). | **PASS**: Spawns isolated sub-agents (`Explore`, `Verification`) returning summary-only text ([arXiv:2604.14228v3](https://arxiv.org/html/2604.14228v3)). | **PARTIAL**: `task` tool spawns sub-sessions, but lacks git worktree isolation and adversarial spot-check gates. | **PARTIAL**: Worker pool (`hermes_state_runtime_workers.py`), but lacks read-only `Explore` (>3 Glob/Grep trigger) and `07_verification_agent.md` rules. | **FAIL**: Single-threaded interactive CLI loop. | **FAIL**: Single-window VS Code extension loop (experimental sub-tasks lack git worktree isolation). | **100% NATIVE PASS**: Native `/goal` Git Worktree Coordinator, auto-triggered Read-Only `Explore` sub-agent (>3 queries $ightarrow$ 1–2K brief), `Compact Service`, and Adversarial Verifier with lead spot-check. |
| **6. Headless & Multi-Session Concurrency** | **PASS**: Supports CLI, JSON, print, RPC, and TypeScript SDK modes (`earendil-works/pi`), though remote CBOR server is marked experimental. | **PASS**: Headless CLI (`-p` / SDK) supporting concurrent processes. | **PASS**: Client-server HTTP/SSE daemon architecture. | **PASS**: Headless daemon, gateway, and CLI (`hermes-dashboard`). | **PARTIAL**: CLI-first; scriptable but not a multi-session RPC daemon. | **FAIL**: Coupled to VS Code GUI extension host. | **100% NATIVE PASS**: Headless async daemon + CLI + JSON-RPC/HTTP-SSE server supporting parallel git-worktree sessions, 5-min TTL heartbeat scheduler, and local policy proxy. |

---

## 3. Deep-Dive Architectural Synthesis: Why We Build `cod.ai` Core with Native Pi Compatibility

### 3.1 What We Adopt Directly from Pi (`earendil-works/pi`) & `@heretek-ai/pi-configs`
Your intuition to look into **Pi** is spot-on. Our OSINT revealed two critical facts:
1. **Pi's Core Design Philosophy is Cache Stability**: As documented in [Inside the Pi Harness](https://rohitghumare.com/blog/inside-the-pi-harness/), Pi is built around a single axiom: *"A harness is a machine for keeping prefixes stable."* Specifically:
   - **Append-Only JSONL Tree (`session.jsonl`)**: Every message entry has an `id` and `parentId`. Branching, rewinding, or switching from Architect exploration to surgical implementation is achieved by moving the active leaf pointer or branching from a common ancestor node—preserving 100% of the cached prefix before the branch point.
   - **Cache-Aware Refusal to Mutate Mid-Transcript**: Pi proved mathematically that deleting a 2,000-token tool output from the middle of a 150,000-token conversation forces the provider to re-bill all 148,000 subsequent tokens at the uncached rate:
     $$\text{Rewrite Cost} \approx T_{\text{surviving}} \times (P_{\text{uncached}} - P_{\text{cache\_read}}) \gg \text{Per-Turn Savings} \approx T_{\text{pruned}} \times P_{\text{cache\_read}}$$
     Therefore, Stage 1 **Micro-Compaction** in `cod.ai` must ONLY prune tool outputs that sit **after the last cached prefix breakpoint** (or batch-prune at the exact moment a new cache breakpoint or Stage 2 compaction occurs), never mutating tokens behind an active cache breakpoint!
   - **The "Cache Re-billed" Telemetry Meter**: Tracking exact dollar and token losses from TTL expirations (`cache miss after >5m idle`) and model switches.
2. **Existing Heretek-AI Investment (`@heretek-ai/pi-configs`)**: Heretek-AI published `@heretek-ai/pi-configs` v1.2.0 on October 24, 2026 ([pi.dev/packages/@heretek-ai/pi-configs](https://pi.dev/packages/@heretek-ai/pi-configs)) with 71 specialist charters (`AGENTS.md`, `.pi/settings.json`, `.pi/hook/hooks.yaml`, `.pi/skills/*/SKILL.md`).

### 3.2 Why Core Pi Alone Cannot Be Used Unmodified (The 4 Gaps)
Despite Pi's strengths, using unmodified `@earendil-works/pi-coding-agent` as the sole foundation violates Constraint #2 in four specific areas:
1. **Runtime Constraint in Current VM**: Upstream `@earendil-works/pi-coding-agent` requires **Node.js $\ge 22.19$** ([earendil-works/pi README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)), whereas our current VM environment has **Python 3.11.2** and **Node.js v18.20.4** (with outbound package installation disabled).
2. **No Built-In 2-Stage Security Classifier or Proxy**: Pi explicitly treats permissions as an "anti-feature" ("There is no permission system at all; the boundary is the container you run it in"). `cod.ai` Phase 5 requires a built-in **2-Stage Auto-Mode Security Classifier** (`12_yolo_auto_mode_classifier.md` + `17_auto_mode_critique.md`) and a credential-isolating **Tool-Call Inspection Proxy**.
3. **No Dual-Polarity Holistic Architect Engine**: Core Pi uses a 20-line CLI prompt. It does not natively implement **Mode A ("Holistic Web Architect")** with zero-tool-noise $n^2$ attention, `<antArtifact>` iterative $>100$-line section-by-section drafting (`Outline -> Section Generation -> Review -> Final`), and GOAL XML framing.
4. **Late Compaction Threshold (~92% vs. 60–80% Attention Budget Governor)**: Core Pi triggers compaction within 16,384 tokens of the context limit, whereas `cod.ai` mandates an **Attention Budget Governor** targeting $60	ext{--}80\%$ capacity combined with Claude Code's 9-section `<summary>` (`21_compact_service.md`) and top-5 recently accessed file restoration.

---

## 4. Decision Gate Verdict & Runtime Selection

### Verdict: **BUILD CUSTOM CORE (`cod.ai`) WITH NATIVE PI-TREE & `@heretek-ai/pi-configs` INTEROPERABILITY**

1. **Primary Implementation Language**: **Python 3.11+ (`asyncio` + `httpx` + `pydantic` + `fastapi`/`uvicorn` + `sqlite3` WAL + `rich`)**, with a companion **TypeScript/Node.js Bridge CLI & Extension Loader** compatible with both Node 18+ (local sandbox) and Node 22+ (`@earendil-works/pi-coding-agent` / `@heretek-ai/pi-configs` in Proxmox production).
   - *Why Python 3.11+ for the Core Daemon & Engine*: Verified present in both the current VM (`Python 3.11.2` with `fastapi`, `httpx`, `pydantic`, `rich`, `click`, `sqlite3` 3.40.1, `selenium`/Chromium) and the target Proxmox VE appliance (`/opt/re-tools-venv`). It allows us to execute, test, and adversarially verify 100% of Phases 2, 3, 4, and 5 immediately inside this VM with zero external dependencies.
   - *Why Native Pi Interoperability*: `cod.ai` will natively read and write Pi's `session.jsonl` tree format (`id`, `parentId`, `retainedTail`) and natively load `@heretek-ai/pi-configs` specialist directories (`agents/<slug>/AGENTS.md`, `.pi/settings.json`, `.pi/hook/hooks.yaml`, `.pi/skills/<skill>/SKILL.md`), allowing all 71 Heretek-AI specialists to run inside `cod.ai`'s Dual-Polarity, Cache-Governed, Proxy-Contained engine!

---

## 5. Target `cod.ai` Architecture Blueprint (Phases 2–5)

```
+--------------------------------------------------------------------------------------------------+
|                                  cod.ai Headless Daemon & CLI                                    |
|                    (Asyncio Core + FastAPI/JSON-RPC Daemon + Pi Tree Session DAG)                |
+--------------------------------------------------------------------------------------------------+
          |                                        |                                      |
          v                                        v                                      v
+-------------------+                    +-------------------+                  +------------------+
| PHASE 2: PROMPT   |                    | PHASE 3: CONTEXT  |                  | PHASE 4: FLEET & |
| & SKILLS ENGINE   |                    | & CACHE ENGINE    |                  | VERIFICATION     |
| (/src/prompts/)   |                    | (/src/context/)   |                  | (/src/agents/)   |
+-------------------+                    +-------------------+                  +------------------+
| - Mode A: Web     |                    | - 3-Layer Prefix  |                  | - /goal Git      |
|   Architect       |                    |   Assembler       |                  |   Worktree Coord |
|   (GOAL XML,      |                    |   (SHA-256 Lock,  |                  | - Read-Only      |
|   >100-line Loop, |                    |   Model Min-Tok   |                  |   Explore Agent  |
|   Skills Playbook)|                    |   Guard: 512/1K/  |                  |   (>3 Glob/Grep  |
| - Mode B: CLI     |                    |   2K/4K)          |                  |   -> 1-2K Brief) |
|   Implementer     |                    | - ToolSearch      |                  | - 2-Tier Compact |
|   (Read/Edit/Write|                    |   (defer_loading  |                  |   (Cache-Safe    |
|   /Glob/Grep only,|                    |   + tool_ref +    |                  |   Micro-Compact  |
|   No-Bash File Op)|                    |   ~200-tok Proxy) |                  |   + 9-Section    |
| - COD_SIMPLE=true |                    | - 5-Min TTL       |                  |   Compact Svc)   |
|   4-Line Benchmark|                    |   Keep-Alive &    |                  | - Atomic Memory  |
| - Native Loader   |                    |   Batch Scheduler |                  |   (if_version)   |
|   for @heretek-ai |                    | - Model-Affinity  |                  | - Adversarial    |
|   /pi-configs     |                    |   Router & 60-80% |                  |   Verifier +     |
|   Specialists     |                    |   Budget Governor |                  |   Spot-Check Gate|
+-------------------+                    +-------------------+                  +------------------+
          \                                        |                                      /
           \---------------------------------------+-------------------------------------/
                                                   |
                                                   v
+--------------------------------------------------------------------------------------------------+
|                     PHASE 5: PROXMOX VM CONTAINMENT PERIMETER & SECURITY                         |
|                                        (/src/security/)                                          |
|  - Tool-Call Inspection Proxy (127.0.0.1 boundary; injects API keys outside agent sandbox)       |
|  - Pluggable Sandbox Driver: Proxmox bwrap + re-firewall (iptables) OR Rootless Process Sandbox  |
|  - 2-Stage Auto-Mode Security Classifier (Stage 1 Fast Rules -> Stage 2 Extended Thinking)       |
|  - `cod auto-mode critique` Rule Auditor + `/skill doctor` Live Cache & Context Telemetry        |
+--------------------------------------------------------------------------------------------------+
```
