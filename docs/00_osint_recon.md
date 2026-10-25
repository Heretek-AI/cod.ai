# Phase 0: OSINT & Environment Reconnaissance (`cod.ai`)

**Document ID:** `00_osint_recon.md`  
**Target Repository:** [Heretek-AI/cod.ai](https://github.com/Heretek-AI/cod.ai)  
**Organization:** [Heretek-AI](https://github.com/Heretek-AI)  
**Date:** October 24, 2026  
**Status:** Verified via Live OSINT & Local System Audit

---

## 1. Executive Summary: Target Repository & Ecosystem Audit creates a Clean-Slate Mandate

Live Open Source Intelligence (OSINT) inspection and local forensic analysis of the attached repository snapshot confirm that [Heretek-AI/cod.ai](https://github.com/Heretek-AI/cod.ai) is a newly initialized, empty public GitHub repository (`octolytics-dimension-repository_public: true`, zero commits, zero branches, zero issues/PRs). Simultaneously, auditing the broader [Heretek-AI](https://github.com/Heretek-AI) organization (106 public repositories) reveals two mature sister initiatives that directly inform `cod.ai`'s architecture:

1. **Pi Specialist Fleet (`@heretek-ai/pi-configs` v1.2.0)**: Published on October 24, 2026 ([pi.dev/packages/@heretek-ai/pi-configs](https://pi.dev/packages/@heretek-ai/pi-configs) / [Heretek-AI/pi-configs](https://github.com/Heretek-AI/pi-configs)), this package implements a 71-specialist local-first multi-agent fleet on top of the [Pi Coding Agent (`earendil-works/pi`)](https://github.com/earendil-works/pi). It already codifies 5 core pillars:
   - Deterministic pre/post tool hooks (`pi-yaml-hooks`, exit-code-2 blocking gates, auto-linters).
   - Lazy proxy-mode MCP runtime (`nicobailon/pi-mcp-adapter` v5.4.0+ collapsing schemas into a ~200-token proxy with QuickJS-WASI `mcpScript` execution).
   - AST/LSP code intelligence (`@juvio15/pi-ast-grep`, `redhat-et/ripwire` saving ~75% tokens, `nikmmd/pi-lsp-adapter`).
   - Isolated child-process RPC subagents (`KristjanPikhof/Pi-Agents-Team` returning only `<final_answer>` blocks).
   - Headless browser & visual critique (`vercel-labs/agent-browser`, `amitpatole/agent-vision`).
2. **Proxmox VE Containment Appliances (`Heretek-AI/ProxmoxVE` & `Heretek-AI/Heretek-ProxmoxVE`)**: Audited via both live GitHub inspection ([Heretek-AI/ProxmoxVE](https://github.com/Heretek-AI/ProxmoxVE)) and the attached `antigravity-re-agent-tests.md` specification. These repositories define the production Proxmox LXC (`ct/re-agent.sh`) and Debian 13 KVM (`vm/re-agent-vm.sh`) containment perimeter:
   - **OS-Level Sandboxing**: `bubblewrap` (`bwrap --unshare-all --ro-bind / / --dev /dev --proc /proc`) with LXC `features: nesting=1,keyctl=1` or full Debian 13 VM isolation.
   - **Network Egress Quarantine (`re-firewall`)**: Dual-stack `iptables` / `ip6tables` (`RE_EGRESS` chain) blocking all direct outbound traffic (`isolate local`) and forcing LLM/MCP traffic through a local Squid/policy proxy at `127.0.0.1:3128` with strict domain allowlisting (e.g., `https://llm.heretek.one/v1`).
   - **Daemon & Service Topology**: Systemd-managed services (`re-firewall`, dashboard bound strictly to `127.0.0.1:9119`, API server on port `8642`).
3. **Multi-Agent Team Rigs (`Heretek-AI/openrig` & `Heretek-AI/heretek-rigs`)**: Forked from `mvschwarz/openrig` ([Heretek-AI/openrig](https://github.com/Heretek-AI/openrig)), demonstrating cross-harness orchestration across Claude Code, Codex, and Pi.

---

## 2. Local VM Hardware, Kernel & Runtime Reconnaissance

Strict execution of `Strict Operational Constraint #1` requires verifying the exact local execution environment rather than assuming capabilities from the prompt persona. Live shell inspection (`uname -a`, `lscpu`, `free -h`, `df -h`, `id`) reveals two distinct operational planes:

| Environment Attribute | Current Execution Sandbox (Live Audit) | Target Production Appliance (`Heretek-AI/ProxmoxVE` Spec) | Architectural Impact on `cod.ai` |
| :--- | :--- | :--- | :--- |
| **Kernel & Virtualization** | `Linux 4.19.0-gvisor #1 SMP x86_64` (gVisor container sandbox) | Proxmox VE Host (`x86_64`) running Debian 13 VM (`qm`) or LXC (`pct`) | `cod.ai` must abstract its sandbox driver (`SandboxDriver`) to support both rootless gVisor/process isolation (current VM) and `bwrap` + `iptables` (`re-firewall`) on Proxmox VE. |
| **OS Distribution** | Debian GNU/Linux 12 (Bookworm) | Debian 12 / Debian 13 (Trixie) | Target POSIX/Linux standard paths and Debian package conventions. |
| **CPU & Memory** | 2 vCPUs (`0,1`), 5.0 GiB RAM (4.7 GiB available), 0 B Swap | Configurable Proxmox LXC/VM resources | Core orchestrator must have minimal idle memory footprint (<100 MB) to allow parallel sub-agent threads and headless Chromium within 4.7 GiB RAM. |
| **Storage & Filesystem** | 20 GiB writable at `/working_dir` and `/home/spark` (18 GiB free); root `/` is read-only | Local ZFS/LVM storage (`/work/cases`, `/opt/*`, `/etc/pve/*`) | All repository files, git worktrees, SQLite WAL state, and `/docs` must reside inside the workspace root (`/working_dir/c_80e02215eb2f8d86/`), with configurable root path overrides. |
| **User & Privileges** | `uid=1235(spark)`, non-root, no passwordless `sudo`, outbound network disabled in shell | `root` (provisioning/firewall) + `analyst` unprivileged user | Do not hardcode `sudo` in core agent loops; use user-space policy proxy and modular containment drivers. |
| **Installed Runtimes** | **Python 3.11.2** (`fastapi`, `httpx`, `pydantic`, `selenium`, `rich`, `click`, `pytest` via unittest, `sqlite3` 3.40.1), **Node.js v18.20.4** (`npm` 9.2.0), **GCC 12.2.0 / G++ 12.2.0**, **Git 2.39.5** (`git worktree` verified), **Chromium 155.0.8059.79**, **tmux** | **Node.js v22**, **Python 3.11+**, **Java 21**, `bwrap`, `iptables`, `squid` (`127.0.0.1:3128`) | **Critical Discovery**: `@earendil-works/pi-coding-agent` requires **Node.js >= 22.19**, while the current sandbox VM has **Node.js v18.20.4** and **Python 3.11.2**. `cod.ai` must either run natively on Python 3.11+ / Node 18+ or provide a zero-dependency core that bridges seamlessly with Pi v1.2+ on Node 22 in production. |

---

## 3. Live Ecosystem OSINT: Anthropic Messages API & Prompt Caching (October 2026 Specs)

Live verification of the official [Anthropic Prompt Caching Documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Context Windows Documentation](https://platform.claude.com/docs/en/build-with-claude/context-windows), [Tool Search Tool Documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool), and [Mid-Conversation System Messages & Tool Changes Documentation](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages) establishes the exact mathematical and protocol rules for `cod.ai`:

### 3.1 Active Model Lineup, Context Windows & Minimum Cacheable Thresholds
As of October 2026, Anthropic's model catalog has expanded to the Claude 4.5–5.5 / Fable / Mythos generations alongside the 4.5 series ([Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Context Windows Docs](https://platform.claude.com/docs/en/build-with-claude/context-windows)):

| Model Identifier | Context Window | Max Output | Base Input / Output ($/MTok) | 5m Cache Write ($/MTok) | 1h Cache Write ($/MTok) | Cache Read / Hit ($/MTok) | Min Cacheable Tokens |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Claude Fable 5.1 / Mythos 5.1** (`claude-fable-5-1`) | 1,000,000 | 128,000 | $10.00 / $50.00 | $12.50 (1.25x) | $20.00 (2.0x) | **$0.25 (0.025x)** | **512 tokens** |
| **Claude Opus 5.5** (`claude-opus-5-5`) | 1,000,000 | 128,000 | $4.00 / $20.00 | $5.00 (1.25x) | $8.00 (2.0x) | **$0.20 (0.05x)** | **512 tokens** |
| **Claude Sonnet 5.5** (`claude-sonnet-5-5`) | 1,000,000 | 128,000 | $2.00 / $10.00 | $2.50 (1.25x) | $4.00 (2.0x) | **$0.10 (0.05x)** | **512 tokens** |
| **Claude Haiku 5.5** (`claude-haiku-5-5`) | 1,000,000 | 128,000 | $0.10 (≤100K) / $0.50 | $0.125 (1.25x) | $0.20 (2.0x) | **$0.01 (0.10x)** | **512 tokens** |
| **Claude Opus 4.8** (`claude-opus-4-8`) | 1,000,000 | 128,000 | $5.00 / $25.00 | $6.25 (1.25x) | $10.00 (2.0x) | $0.50 (0.10x) | **1,024 tokens** |
| **Claude Opus 4.7** (`claude-opus-4-7`) | 1,000,000 | 128,000 | $5.00 / $25.00 | $6.25 (1.25x) | $10.00 (2.0x) | $0.50 (0.10x) | **2,048 tokens** |
| **Claude Opus 4.6 / 4.5** (`claude-opus-4-6`, `claude-opus-4-5`) | 1M (4.6) / 200K (4.5) | 128K / 64K | $5.00 / $25.00 | $6.25 (1.25x) | $10.00 (2.0x) | $0.50 (0.10x) | **4,096 tokens** |
| **Claude Sonnet 5 / 4.6 / 4.5** (`claude-sonnet-4-6`) | 1M (5, 4.6) / 200K (4.5) | 128K / 64K | $2.00–$3.00 / $10–$15 | $2.50–$3.75 | $4.00–$6.00 | $0.20–$0.30 (0.10x) | **1,024 tokens** |
| **Claude Haiku 4.5** (`claude-haiku-4-5`) | 200,000 | 64,000 | $1.00 / $5.00 | $1.25 (1.25x) | $2.00 (2.0x) | $0.10 (0.10x) | **4,096 tokens** |

*Key Verification Note*: While the user prompt notes minimum thresholds of $1,024+$ for Sonnet/Opus and $2,048+$ for Haiku (which held for earlier 3.5/4.0 generations), live OSINT proves that **Claude Opus 4.5/4.6 and Haiku 4.5 actually require 4,096 tokens**, **Opus 4.7 requires 2,048 tokens**, **Sonnet 4.5/4.6/5 and Opus 4.8 require 1,024 tokens**, and **5.5-generation models require 512 tokens** ([Prompt Caching Limitations](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). Therefore, `cod.ai`'s Cache-Control Assembler must maintain a **model-aware threshold table** (enforcing $\ge 4,096$ tokens when targeting Opus 4.5/4.6 or Haiku 4.5, and $\ge 1,024$ / $2,048$ / $512$ dynamically per model ID) so cache breakpoints never silently fail!

### 3.2 Prefix Hash Hierarchy, 20-Block Lookback Window & TTL Mechanics
1. **Strict Prefix Ordering**: Anthropic hashes prompts in the exact sequence: `tools` $ightarrow$ `system` $ightarrow$ `messages` ([Prompt Caching Structure](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). Any byte modification in `tools` invalidates `tools`, `system`, and `messages`. Any modification in `system` invalidates `system` and `messages`.
2. **Up to 4 Explicit Breakpoints + Automatic Caching**: The API supports up to 4 explicit `cache_control: {"type": "ephemeral"}` block breakpoints (plus optional `"ttl": "1h"`), or top-level automatic caching.
3. **The 20-Block Lookback Window**: When checking a breakpoint, the API walks backward at most **20 blocks** from the breakpoint to find a prior cache write ([Automatic Prefix Checking](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). Consecutive `tool_use` or `tool_result` blocks count as 1 position. If a turn adds $>20$ blocks without an intermediate breakpoint, the lookback misses!
4. **5-Minute TTL Measurement Trap**: The 300-second (5-minute) lifetime is measured from the **start of the request** that writes or reads the cache entry, **not** from the end of streaming ([How Prompt Caching Works](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). If an Architect turn takes 180 seconds to stream, the user has only **120 seconds** remaining before the prefix expires!
5. **Thinking Block Preservation**: On Opus 4.5+, Sonnet 4.6+, and Haiku 5.5, previous thinking blocks are preserved in context by default and cached alongside assistant turns. Modifying or dropping a preserved thinking block (or altering a message before it) invalidates the cache from that position onward and triggers a cryptographic signature validation error.

### 3.3 Deferred Tool Loading (`ToolSearch`) & Mid-Conversation System/Tool Injection
Anthropic now provides two complementary cache-preserving mechanisms that `cod.ai` must support in tandem:
1. **Native `defer_loading: true` + `ToolSearch` (`tool_search_tool_regex_20251119` / `tool_search_tool_bm25_20251119`)**:
   - Tools marked with `"defer_loading": true` in the top-level `tools` array are **excluded from the initial system-prompt prefix** ([Tool Search Tool Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)).
   - At least one non-deferred tool (e.g., the `ToolSearch` tool plus the 4–5 core file primitives) must remain `defer_loading: false` and carry the `cache_control` breakpoint (since a tool with `defer_loading: true` cannot carry `cache_control`).
   - When the model searches, the API (or custom client-side handler) returns `tool_reference` blocks inside `tool_result`, expanding the full schema inline at the tail of Layer 3 without touching Layer 1!
2. **Mid-Conversation `role: "system"` Messages & `tool_addition` (`inline-tools-2026-09-15`)**:
   - On Opus 4.8/5/5.5, Sonnet 5.5, Haiku 5.5, and Fable/Mythos, appending `{"role": "system", "content": "..."}` (with optional `clear_at: "next_user_message"` under beta header `mid-conversation-system-clear-at-2026-08-21`) or `tool_addition` blocks (`inline-tools-2026-09-15`) injects operator-level rules or dynamic MCP schemas at the end of `messages` with zero prefix cache invalidation ([Mid-Conversation System Messages Docs](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)).
   - For universal compatibility across all models (including Sonnet 4.5/4.6/5 and OpenAI-compatible local endpoints like `llm.heretek.one`), `cod.ai` also supports injecting `<system_reminder>` tags inside the final user/tool-result turn in Layer 3.

---

## 4. Live Ecosystem OSINT: Model Context Protocol (MCP) Specifications

Inspection of the latest [Model Context Protocol (MCP) Specification (Version 2026-07-28)](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) confirms:
1. **`stdio` Transport**: Client launches the MCP server as a subprocess and exchanges UTF-8 newline-delimited JSON-RPC 2.0 messages over `stdin`/`stdout`. Cancellation uses `notifications/cancelled`. Custom local transports over Unix domain sockets or TCP should reuse `stdio` newline-delimited JSON-RPC framing.
2. **`Streamable HTTP` Transport (replaces legacy dual-endpoint HTTP+SSE from `2024-11-05`)**:
   - Introduced in `2025-03-26` and refined in `2026-07-28`, every client message is an HTTP `POST` to a **single MCP endpoint**.
   - Replies arrive either as a single JSON object (`application/json`) or a request-scoped Server-Sent Events (`text/event-stream`) stream.
   - Protocol version and capabilities travel in `_meta.io.modelcontextprotocol/*` inside the JSON-RPC body and are mirrored into HTTP headers for proxy inspection.
   - Cancellation is signaled by closing the request's response stream or sending `notifications/cancelled`.
   - Backward compatibility with legacy `2024-11-05` HTTP+SSE servers requires probing `POST` first and falling back to `GET` SSE endpoint discovery if a `4xx` is returned.

---

## 5. Live Ecosystem OSINT: Open-Source Coding Harnesses Audit

We audited six major coding harnesses against how they assemble prompts, manage context windows, load tools, and isolate sub-agents:

1. **Claude Code CLI/SDK (Anthropic, v2.1.220 / March–July 2026 Source Analysis)**:
   - **Prompt Assembly**: Assembles a 3-layer stack ordered by volatility: Layer 1 (System prompt ~4,200 tokens + core tools + `ToolSearch`), Layer 2 (`CLAUDE.md` hierarchy injected as a user message after the system prompt), and Layer 3 (append-only conversation history with `<system-reminder>` tags for file edits and mode changes) ([Inside the Claude Code Harness](https://rohitghumare.com/blog/inside-the-claude-code-harness/), [Dive into Claude Code arXiv:2604.14228v3](https://arxiv.org/html/2604.14228v3)).
   - **Compaction**: Implements a 5-stage pipeline (Snip compact $ightarrow$ Microcompact stripping old tool results $ightarrow$ Context collapse $ightarrow$ Auto-compact structured 9-section `<summary>` with `<analysis>` scratchpad stripped $ightarrow$ Reactive emergency compact).
   - **Flaws / Limitations for `cod.ai`**: Proprietary closed-source license; its default `01_main_system_prompt.md` enforces rigid anti-abstraction rules ("no unasked helpers", "three similar lines over premature abstraction") that cripple greenfield system design; furthermore, its aggressive Stage 1/2 micro-compaction mutates middle-of-history tool results if not aligned with cache breakpoints.
2. **Pi Coding Agent (`@earendil-works/pi-coding-agent` / `@mariozechner/pi-coding-agent` v1.2.0+) + `@heretek-ai/pi-configs`**:
   - **Prompt Assembly**: Ultra-minimal ~20-line static system prompt with **zero timestamps, dates, or random tokens** in the prefix ([Inside the Pi Harness](https://rohitghumare.com/blog/inside-the-pi-harness/), [earendil-works/pi README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)). Walks ancestor directories for `AGENTS.md`/`CLAUDE.md` with git worktree deduplication.
   - **DAG Session Tree (`session.jsonl`)**: Stores every turn as a tree node (`id`, `parentId`). Rewinding or branching (`/tree`) simply moves the active leaf pointer without deleting history or invalidating the cached prefix prior to the branch point!
   - **Cache Telemetry ("The Meter")**: Tracks exact `Cache Re-billed: $X (Y tokens, Z misses)` and attributes causes (`cache miss after model switch`, `cache miss after 12m idle`). Sends one-shot compaction summaries with caching disabled (`skipCacheWrite`) and a fresh session ID.
   - **Additive Tool Loading**: Supports `defer_loading` + `tool_reference` on Anthropic and `nicobailon/pi-mcp-adapter` (~200-token proxy tool + QuickJS-WASI `mcpScript` execution in `@heretek-ai/pi-configs`).
   - **Flaws / Limitations for `cod.ai`**: Core Pi deliberately omits built-in permission classifiers ("no permission system at all"), native sub-agent coordinators, Dual-Polarity Architect vs. Implementer prompt switching, and the 5-minute TTL active keep-alive scheduler—relying entirely on external extensions (`@heretek-ai/pi-configs`) and requiring Node.js $\ge 22.19$.
3. **OpenCode (`anomalyco/opencode` / `sst/opencode`)**:
   - **Architecture**: Client-server TypeScript runtime with TUI and `task` subagent tool ([Inside OpenCode](https://medium.com/@falexm/inside-opencode-understanding-the-architecture-behind-the-ai-runtime-01236d9370ff)).
   - **Critical Cache Bug Confirmed via Live OSINT**: Issue [#58485 (`Moving plan/build reminders invalidate the prompt cache and increase API costs`)](https://github.com/anomalyco/opencode/issues/58485) (filed October 23, 2026) proves that OpenCode moves/mutates plan and build reminder blocks across turns, invalidating the prompt cache and spiking API costs.
4. **NousResearch Hermes Agent (`NousResearch/hermes-agent`)**:
   - **Architecture**: Python-based agent (`hermes_state_*.py`, SQLite WAL state, `bubblewrap` terminal backend, `holographic` memory provider) used in `Heretek-AI/ProxmoxVE` (`ct/re-agent.sh`).
   - **Flaws / Limitations for `cod.ai`**: Built as a general-purpose persistent assistant/reverse-engineering agent rather than a dual-polarity software architecture and surgical coding harness; lacks native `ToolSearch` `tool_reference` expansion and strict 3-layer byte-identical prefix guarantees.
5. **Aider (`Aider-AI/aider`)**:
   - **Architecture**: Python CLI using Tree-sitter PageRank Repository Maps ([Aider Repo Map](https://aider.chat/docs/repomap.html)) and `--cache-prompts` with optional `--cache-keepalive-pings` ([Aider Prompt Caching](https://aider.chat/docs/usage/caching.html)).
   - **Flaws / Limitations for `cod.ai`**: Dynamically recalculates and mutates the repo map and active file list inside the prompt prefix as files are added/dropped, frequently invalidating the cache; lacks MCP `ToolSearch`, multi-agent clean-context spawning, and headless daemon concurrency.
6. **Cline (`cline/cline`)**:
   - **Architecture**: VS Code extension with `ContextManager` and `FileContextTracker` ([Dissecting Cline Context Management](https://medium.com/@balajibal/dissecting-cline-cline-context-management-260aec3d84cb)).
   - **Flaws / Limitations for `cod.ai`**: Coupled to VS Code GUI; injects all MCP tool definitions upfront into the system prompt (confirmed in [Cline Discussion #8578](https://github.com/cline/cline/discussions/8578)), causing massive schema bloat and cache invalidation whenever MCP servers connect.
