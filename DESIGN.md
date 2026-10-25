# Phase 6: `claude.ai` Web (Claude Opus 5.5) Visual & OSINT Style Guide (`DESIGN.md`)

**Document ID:** `04_claude_web_opus_5_5_style_guide.md`  
**Target Repository:** [Heretek-AI/cod.ai](https://www.google.com/search?q=https://github.com/Heretek-AI/cod.ai)  
**Grounded Sources:** [Claude Design System (`shadcn.io/design/claude`)](https://www.shadcn.io/design/claude), [Anthropic Design System (`shadcn.io/design/anthropic`)](https://www.shadcn.io/design/anthropic), [Claude Opus 5.5 Effort Specification](https://platform.claude.com/docs/en/build-with-claude/effort), [Claude Opus 5.5 Adaptive Thinking Specification](https://platform.claude.com/docs/en/build-with-claude/thinking)  
**Date:** October 25, 2026

---

## 1. Visual Philosophy: Warm Literary Editorialism vs. Cold SaaS Chrome

Live OSINT across the [Claude Product Design System](https://www.shadcn.io/design/claude) and [Anthropic Brand System](https://www.shadcn.io/design/anthropic) establishes why `claude.ai` Web feels fundamentally calmer and more holistic than developer IDEs:

1. **No Cool Grays or Pure White (`#ffffff`) Canvas**: `claude.ai` anchors its entire surface hierarchy on a warm, paper-tinted **Ivory Cream Canvas (`#faf9f5`)** in Light Mode and a warm **Obsidian Ink Canvas (`#181715`)** in Dark Mode.
2. **Surface Contrast Instead of Drop Shadows**: Cards, chat composer boxes, and sidebars lift off the canvas through subtle warm cream steps (`#f5f0e8` $\rightarrow$ `#efe9de` $\rightarrow$ `#e8e0d2`) and `1px` warm hairlines (`#d1cfc5`), avoiding heavy drop-shadows or neon glows.
3. **Editorial Serif + Humanist Sans + Technical Mono Triad**:
   - **Display & Assistant Prose (`Copernicus` / `Tiempos Text` / `Cormorant Garamond` / `Newsreader` / `Georgia`)**: Assistant responses and section headers read like a typeset literary essay (`weight: 400`, `line-height: 1.65`, `-0.015em` tracking), encouraging deep reading and holistic architectural review.
   - **UI Chrome, Navigation & User Prompts (`StyreneB` / `Inter`)**: Clean humanist sans-serif (`weight: 400–500`) for sidebar items, model selectors, pills, and user messages.
   - **Code, Telemetry & Eyebrow Metadata (`Anthropic Mono` / `JetBrains Mono`)**: Used for `<antArtifact>` code views, SHA-256 cache locks, token counters, and uppercase eyebrow tags.
4. **Sparing Terracotta Coral Voltage (`#cc785c` / `#d97757`)**: Primary CTAs, active send buttons, and the Claude spark emblem use warm terracotta coral (`#cc785c`, active `#a9583e`), paired with muted secondary accents from Anthropic's `:root` research palette: **Sage Cactus (`#bcd1ca`)**, **Olive (`#788c5d`)**, **Sky (`#6a9bcc`)**, **Fig (`#c46686`)**, and **Heather (`#cbcadb`)**.

---

## 2. Exact Color Token Specification (`:root` CSS Variables)

| Token Name | CSS Variable | Light Mode Hex (`Cream`) | Dark Mode Hex (`Obsidian`) | Component / Surface Usage |
| :--- | :--- | :--- | :--- | :--- |
| **Canvas Default** | `--bg-canvas` | `#faf9f5` | `#181715` | Main chat viewport background |
| **Surface Soft (Sidebar)** | `--bg-surface-soft` | `#f5f0e8` | `#1f1e1b` | Left collapsible navigation & session tree drawer |
| **Surface Card (Composer)** | `--bg-surface-card` | `#efe9de` | `#252320` | Floating prompt composer, Artifact cards, Thinking drawer |
| **Surface Strong (Hover)** | `--bg-surface-strong` | `#e8e0d2` | `#2f2d29` | User message bubble, active pill hover, tab bar |
| **Code Editor Surface** | `--bg-code-surface` | `#181715` | `#111110` | `<antArtifact>` code view & live cURL/JSON payload inspector |
| **Primary Coral** | `--accent-primary` | `#cc785c` | `#d97757` | Primary Send CTA, active artifact badge, brand spark |
| **Primary Coral Active** | `--accent-primary-active` | `#a9583e` | `#c6613f` | Button press / hover state |
| **Primary Disabled** | `--accent-disabled` | `#e6dfd8` | `#3a3733` | Disabled send button when input is empty |
| **Ink Primary** | `--text-ink` | `#141413` | `#faf9f5` | Headlines, primary assistant prose, active controls |
| **Body Secondary** | `--text-body` | `#3d3d3a` | `#d1cfc5` | Standard body copy, thinking summary text |
| **Muted Metadata** | `--text-muted` | `#6c6a64` | `#a09d96` | Timestamps, token counts, model subtitles |
| **Muted Soft** | `--text-muted-soft` | `#8e8b82` | `#78756e` | Input placeholders, inactive icons |
| **Hairline Border** | `--border-hairline` | `#d1cfc5` | `#33312d` | `1px solid` card, composer, and split-pane dividers |
| **Semantic Olive (Pass)** | `--accent-olive` | `#788c5d` | `#8fa870` | Cache Hit, 5-Min TTL Hot, Verifier `VERDICT: PASS` |
| **Semantic Sky (Info)** | `--accent-sky` | `#6a9bcc` | `#7eb0e2` | Mode A Architect badge, `ToolSearch` reference expansion |
| **Semantic Fig (Warn/Deny)** | `--accent-fig` | `#c46686` | `#d97a9a` | TTL Pre-Expiration Warning, Classifier `SOFT_DENY` |

---

## 3. Typography & Spacing Scale

| Token Tier | Font Family | Size / Line-Height | Weight / Tracking | Application in `cod.ai` Web GUI |
| :--- | :--- | :--- | :--- | :--- |
| **`display-greeting`** | `'Cormorant Garamond', 'Newsreader', Georgia, serif` | `36px` / `1.15` | `400` / `-0.5px` | Centered session greeting (*"Good evening, Argon. What shall we architect?"*) |
| **`heading-artifact`** | `'Cormorant Garamond', Georgia, serif` | `22px` / `1.3` | `500` / `-0.3px` | `<antArtifact>` header title & modal headings |
| **`prose-assistant`** | `'Newsreader', Georgia, serif` | `16.5px` / `1.68` | `400` / `-0.01em` | Long-form assistant architectural prose & explanations |
| **`ui-body`** | `'Inter', system-ui, sans-serif` | `14px` / `1.45` | `400–500` / `0px` | User message bubbles, sidebar items, settings controls |
| **`mono-telemetry`** | `'JetBrains Mono', monospace` | `12px` / `1.4` | `500` / `0.04em` | 3-Layer cache hashes, 5-min TTL clock, `Cache Re-billed` meter, code |

- **Corner Radius Ladder**: `4px` (inline code & micro-badges), `8px` (buttons, selector pills, tabs), `12px` (Artifact preview cards, thinking accordions), `16px` (floating prompt composer & modals), `9999px` (model & effort pills).
- **Reading Column & Split Layout**: When the `<antArtifact>` workbench is closed, the chat column centers at `max-width: 740px`. When an Artifact is opened, the viewport smoothly splits `50% / 50%` (`chat` left, `Artifact & Telemetry Workbench` right).

---

## 4. Verified Claude Opus 5.5 UX & API Controls (`Effort` + `Adaptive Thinking` + `Custom Endpoint`)

Grounded in the [Claude Effort Documentation](https://platform.claude.com/docs/en/build-with-claude/effort) and [Claude Thinking Documentation](https://platform.claude.com/docs/en/build-with-claude/thinking):

1. **Five-Tier Effort Selector (`output_config.effort`)**:
   - Supports `low`, `medium` (**verified default on `claude-opus-5-5` and `claude-haiku-5-5`**), `high` (default on `claude-sonnet-5-5` and `claude-fable-5-1`), `xhigh` (long-horizon 30+ min coding), and `max` (unconstrained frontier reasoning).
   - **Cache-Preserving Per-Message Effort**: Changing effort mid-conversation emits a `{"role": "system", "content": [], "output_config": {"effort": "<level>"}}` block with beta header `mid-conversation-output-config-2026-07-01` so the cached prefix is never invalidated!
2. **Adaptive Thinking Control (`thinking: {"type": "adaptive", "display": "..."}`)**:
   - On `claude-opus-5-5`, adaptive thinking is always active (`thinking: {"type": "disabled"}` returns HTTP 400).
   - Exposes the 3 official `display` modes:
     - `"summarized"` (streams readable `thinking_delta` summaries + `signature_delta`).
     - `"updates"` (streams concise inter-tool progress updates via `thinking-display-updates-2026-08-18`).
     - `"omitted"` (fastest time-to-first-token; returns encrypted `signature` only).
3. **Universal Custom Endpoint Studio**:
   - Allows users to configure any target endpoint directly in the UI (`localStorage`-persisted + instant connection tester + live request payload preview):
     - **Preset 1 — Anthropic Official API**: `https://api.anthropic.com/v1/messages` (`anthropic-version: 2023-06-01`, native `cache_control` & `output_config.effort`).
     - **Preset 2 — Heretek-AI Proxmox Quarantine Gateway**: `https://llm.heretek.one/v1` (routed via local `re-firewall` proxy `127.0.0.1:3128`, supporting both Anthropic and OpenAI wire formats, plus `lemonade-CyberTielCoder` / Opus 5.5).
     - **Preset 3 — Local `cod.ai` FastAPI / Ollama / vLLM / OpenRouter Endpoint**: Any custom URL (e.g., `http://127.0.0.1:8642/v1/messages` or `http://localhost:11434/v1/chat/completions`), custom model ID, custom headers, and automatic fallback to rich local architectural synthesis when running offline in sandboxed environments.
