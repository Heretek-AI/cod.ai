---
name: pi_specialist_bridge
domain: orchestration
polarity: BOTH
description: Native interoperability playbook for loading @heretek-ai/pi-configs specialist charters and hooks without breaking prefix caches.
---
# Pi Specialist Bridge Playbook (`@heretek-ai/pi-configs` Integration)

## 1. Cache-Safe Charter Injection
- Never mutate Layer 1 (the static system prompt) when switching to one of the 74 `@heretek-ai/pi-configs` specialists.
- Always inject the specialist's `AGENTS.md` charter and `.pi/skills/*/SKILL.md` rules at the tail of Layer 3 via a mid-conversation `role: "system"` block or `<system_reminder type="specialist_charter_switch">` tag.
- Honor all `.pi/hook/hooks.yaml` `tool.before.*` and `file.changed` rules deterministically, aborting unauthorized actions with exit code `2`.
