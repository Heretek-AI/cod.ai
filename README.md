# `cod.ai` — Next-Generation Agentic Coding Harness & Orchestration Platform

[![Verdict: PASS](https://img.shields.io/badge/Adversarial_Verifier-VERDICT:_PASS-brightgreen)](docs/03_verification_and_architecture_report.md)
[![Pi-Configs Compatible](https://img.shields.io/badge/Pi_Ecosystem-@heretek--ai/pi--configs_v1.3.0-blue)](docs/02_pi_configs_tracking_issue.md)

`cod.ai` ([Heretek-AI/cod.ai](https://github.com/Heretek-AI/cod.ai)) unifies the **holistic, zero-noise $n^2$ architectural synthesis** of `claude.ai` Web (`<antArtifact>` + Skills Playbooks + $>100$-line iterative drafting) with the **surgical Just-In-Time (JIT) execution, byte-identical 3-layer prefix caching, Pi JSONL session DAGs, and adversarial sub-agent verification** of Claude Code and [Pi (`earendil-works/pi`)](https://github.com/earendil-works/pi).

---

## Repository Structure

```text
cod.ai/
├── README.md                                  # Quickstart, architecture overview & CLI guide
├── CLAUDE.md                                  # Layer 2 static project context & invariant contract
├── AGENTS.md                                  # Multi-agent specialist charter & Pi interoperability spec
├── pyproject.toml                             # Python 3.11+ package & CLI entrypoint (`cod`)
├── .gitignore                                 # Standard Python/Node/worktree ignores
├── docs/
│   ├── 00_osint_recon.md                      # Phase 0: Live OSINT & Proxmox VM Reconnaissance
│   ├── 01_harness_decision_matrix.md          # Phase 1: Six-Invariant Harness Evaluation Matrix (ADR-001)
│   ├── 02_pi_configs_tracking_issue.md        # Phase 1.5: Tracking issue & PR spec for Heretek-AI/pi-configs
│   └── 03_verification_and_architecture_report.md # Phases 2-5 Adversarial Verification & Telemetry Report
├── skills/
│   ├── system_architecture/SKILL.md           # Mode A Distributed Systems & Module Decomposition Playbook
│   ├── frontend_ux/SKILL.md                   # Mode A High-Craft UI/UX & WCAG 2.2 AA Playbook
│   ├── systems_security/SKILL.md              # Proxmox Containment, Proxy Vault & Classifier Playbook
│   └── pi_specialist_bridge/SKILL.md          # Cache-Safe @heretek-ai/pi-configs Charter Loader Playbook
├── src/
│   ├── __init__.py
│   ├── cli.py                                 # Unified `cod` Headless CLI (`cod doctor`, `cod auto-mode critique`, `cod simple`)
│   ├── prompts/                               # Phase 2: Dual-Polarity Prompt Engine
│   │   ├── architect_mode.py                  # Mode A: GOAL XML framing + >100-line 4-stage iterative loop + anti-truncation
│   │   ├── implementer_mode.py                # Mode B: Read/Edit/Write/Glob/Grep enforcement + Bash file-op blocker
│   │   ├── simple_mode.py                     # COD_SIMPLE=true 4-line minimal benchmark prompt
│   │   └── engine.py                          # Unified PromptAssemblyEngine + @heretek-ai/pi-configs loader
│   ├── context/                               # Phase 3: Token Economics, Prefix Cache & Hybrid Retrieval
│   │   ├── cache_assembler.py                 # 3-Layer Cache-Control Assembler + ToolSearch (`defer_loading: true`)
│   │   ├── ttl_scheduler.py                   # 5-Minute TTL Keep-Alive & Batching Scheduler (from request start)
│   │   └── router_and_retrieval.py            # Model-Affinity Router + 60-80% Attention Budget Governor
│   ├── agents/                                # Phase 4: Multi-Agent Fleet, Compaction & Adversarial Verifier
│   │   ├── session_dag.py                     # Pi-compatible `session.jsonl` Tree DAG + `Cache Re-billed` meter
│   │   ├── coordinator.py                     # `/goal` Git Worktree Coordinator (`git worktree add -b`)
│   │   ├── explore_agent.py                   # Read-Only `Explore` Sub-Agent (>3 Glob/Grep -> 1-2K token brief)
│   │   ├── compaction.py                      # Two-Tier Compaction (Stage 1 Cache-Safe Micro + Stage 2 9-Section Compact)
│   │   ├── memory.py                          # Atomic `memory_str_replace` (`if_version` guard) + `NOTES.md` / `TodoWrite`
│   │   └── verifier.py                        # Adversarial Verification Agent (`07_verification_agent.md` + Lead Spot-Check)
│   └── security/                              # Phase 5: Proxmox VM Containment & Security Classifier
│       ├── proxy_sandbox.py                   # 127.0.0.1 Credential Vault Proxy + `bwrap` / rootless sandbox runner
│       ├── classifier.py                      # 2-Stage Auto-Mode Security Classifier + `cod auto-mode critique`
│       └── telemetry.py                       # `/skill doctor` & Live Context Quality Telemetry Dashboard
├── pi_configs_upstream/                       # Drop-in upgrade for https://github.com/Heretek-AI/pi-configs (v1.3.0)
│   ├── create_tracking_issue.sh               # One-click script to open the tracking issue on Heretek-AI/pi-configs
│   ├── src/cod_ai_invariant_bridge.ts         # TypeScript extension fixing `/specialist` Layer-3 cache preservation
│   └── agents/                                # Custom specialists (#72 holistic-web-architect, #73 attention-budget-governor, #74 adversarial-verifier)
└── tests/
    └── test_cod_ai_full_suite.py              # 16 end-to-end unit & integration tests across Phases 2-5
```

---

## Quickstart & Verification

```bash
# 1. Run the complete 16-test automated verification suite
PYTHONPATH=. python3 tests/test_cod_ai_full_suite.py

# 2. Run `/skill doctor` & live telemetry dashboard
PYTHONPATH=. python3 src/cli.py doctor

# 3. Audit permission rules with `cod auto-mode critique`
PYTHONPATH=. python3 src/cli.py auto-mode critique

# 4. Emit the 4-line `COD_SIMPLE=true` minimal benchmark prompt
PYTHONPATH=. python3 src/cli.py simple

# 5. Open the upstream tracking issue on Heretek-AI/pi-configs
GITHUB_TOKEN=ghp_your_token ./pi_configs_upstream/create_tracking_issue.sh
```
