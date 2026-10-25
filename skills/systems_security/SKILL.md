---
name: systems_security
domain: security
polarity: BOTH
description: Proxmox VE defense-in-depth containment, credential proxy isolation, and 2-stage auto-mode security classification.
---
# Systems Security & Containment Playbook (`cod.ai` Mode A & Mode B)

## 1. Defense-in-Depth Invariants
- **Zero Raw Credential Exposure**: Never pass raw API keys (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `API_SERVER_KEY`) into the agent's readable environment or filesystem. Inject authentication headers strictly at the `127.0.0.1` policy proxy boundary.
- **Shell Operator Decomposition**: Parse every composite shell command (`|`, `&&`, `;`, `$()`, backticks) and evaluate each subcommand independently against `allow` and `soft_deny` rules.
- **Least-Privilege Filesystem & Network**: Enforce `bwrap --unshare-all` (or rootless process isolation) and restrict outbound network traffic to allowlisted endpoints (`re-firewall`).
