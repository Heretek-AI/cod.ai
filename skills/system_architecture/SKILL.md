---
name: system_architecture
domain: architecture
polarity: MODE_A_HOLISTIC_ARCHITECT
description: Battle-tested distributed systems, modular decomposition, and cache-preserving orchestration patterns.
---
# System Architecture Playbook (`cod.ai` Mode A)

## 1. Core Architectural Rules
- **Strict Separation of Concerns**: Decouple state storage (append-only DAG JSONL / SQLite WAL), prompt assembly (immutable Layer 1 & Layer 2 prefixes), tool execution, and containment proxies.
- **Explicit Trade-Off Analysis**: Every design must evaluate latency, token cost (cache write vs. read multipliers), blast radius, and failure recovery before selecting an implementation pattern.
- **Complete Interface Contracts**: Define strict typed schemas (Pydantic models / TypeScript interfaces) for all inter-module boundaries before writing business logic.
- **Zero-Truncation Mandate**: Every file or specification >100 lines must follow the 4-stage iterative drafting loop (Outline -> Section-by-Section Generation -> Review & Refine -> Final Output) with zero placeholder comments.
