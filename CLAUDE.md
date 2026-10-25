# `CLAUDE.md` — Static Layer 2 Project Context (`cod.ai`)

## Architectural Authorizations (`Mode B` Override)
- `authorize_modular_helpers`: Explicitly permitted when implementing multi-phase orchestration engines.
- `authorize_boundary_validation`: Explicitly required at all API, proxy, and memory concurrency boundaries.
- `authorize_clean_abstractions`: Explicitly authorized by Mode A Architect specifications.

## Six Non-Negotiable Architectural Invariants
1. **Byte-Identical Static Prefix Guarantee**: Never mutate Layer 1 (`tools` + `system`) or Layer 2 (`CLAUDE.md` + `AGENTS.md`) mid-session. Inject all dynamic reminders, specialist charters, and newly discovered schemas at the tail of Layer 3.
2. **Deferred Tool Schema Loading (`ToolSearch`)**: Keep `defer_loading: true` on all extended/MCP tools; place `cache_control` only on non-deferred blocks.
3. **Dual-Polarity Mode Switching**: Use Mode A (`HolisticWebArchitectEngine`) for $>100$-line iterative design and Mode B (`SurgicalCLIImplementer`) for repository execution.
4. **Attention Budget Governor ($60\text{--}80\%$)**: Maintain full in-context $n^2$ self-attention up to 60% capacity; trigger `project_knowledge_search` and Two-Tier Compaction before 80%.
5. **Multi-Agent Clean-Context Spawning**: Spawn `ReadOnlyExploreSubAgent` whenever discovery exceeds 3 `Glob`/`Grep` queries, and verify via `AdversarialVerificationAgent` (`07_verification_agent.md`).
6. **Proxmox Containment & Credential Isolation**: Keep raw API keys inside `CredentialVaultProxy` (`127.0.0.1:3128`) outside the agent's readable environment.
