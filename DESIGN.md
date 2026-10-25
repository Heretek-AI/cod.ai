# Design

## Terminal agent

`cod` runs `src/agent/engine.py`, a tool-use loop over the streaming Messages API. One user turn works like this:

1. The prompt is appended to the session and the whole history is sent with the six tool definitions.
2. Text and thinking stream to the terminal as they arrive.
3. If the response stops for `tool_use`, each call is checked against the permission policy (deny, allow, or ask the user), run, and its result sent back in the next request. This repeats until Claude ends its turn, up to 50 rounds.
4. Every message is written to `.cod/sessions/<id>.jsonl` as soon as it is final.

The request uses the same settings as the web chat (table below) plus `tools` (each client tool with `eager_input_streaming: true`, then the `memory_20250818` tool) and server-side compaction: `context_management` with a `compact_20260112` edit triggered at 150,000 input tokens, under beta `compact-2026-01-12`. When it triggers, the response starts with a `compaction` block. That block is stored with the rest of the assistant content and sent back unchanged, and the API reads the conversation from it onward. The system prompt (base instructions, the project root, and the project's `CLAUDE.md` and `AGENTS.md`) is built when the session starts and stored in its header, and so is whether the memory tool is on, so the tool list never changes, so every request in a session shares a cacheable prefix, including after a resume.

| Stop reason | Handling |
| :--- | :--- |
| `end_turn` | The turn ends. |
| `tool_use` | Run the calls and continue. |
| `max_tokens` | Tool calls in the cut-off response are not run; each gets an error result asking for a smaller input. Without tool calls the turn ends with a note. |
| `pause_turn` | The history is sent back unchanged to resume. |
| `refusal` | The turn's messages, starting with the user's prompt, are rolled back so the user can rephrase. |

If the user interrupts while tools are running, the calls that finished keep their results and the rest get an "interrupted" error result, so the history stays valid.

## Web chat

`cod serve` runs a local chat interface for the Claude Messages API. It has two parts: `src/web_server.py`, a FastAPI server, and `web/index.html`, a single page with no build step and no framework.

### Request flow

1. The page loads `/api/config` for the model list, effort levels and per-model default effort.
2. On send, the page posts the whole conversation to `POST /api/chat` together with the chosen model, effort and thinking display.
3. The server validates the request, adds the system prompt, and opens a streaming request with the Anthropic SDK (`client.beta.messages.stream`). It relays the stream to the browser as server-sent events.
4. When the turn finishes, the server sends the assistant content to store in the history. The page appends it and sends it back unchanged on the next turn.

The API key never reaches the browser. The SDK resolves credentials on the server (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or an `ant auth login` profile), and `ANTHROPIC_BASE_URL` can point it at a gateway.

### API request

| Field | Value |
| :--- | :--- |
| `model` | One of `claude-opus-5-5` (default), `claude-fable-5-1`, `claude-sonnet-5-5`, `claude-haiku-5-5` |
| `max_tokens` | `64000`, streamed |
| `system` | Base prompt plus `CLAUDE.md` and `AGENTS.md`, built once at startup so it is byte-identical on every request (`COD_PROJECT_CONTEXT=0` drops the files) |
| `thinking` | `{"type": "adaptive", "display": "summarized" \| "omitted"}` |
| `output_config.effort` | The selected level, or the model's default (`medium` on Opus 5.5 and Haiku 5.5, `high` otherwise) |
| `cache_control` | Top-level `{"type": "ephemeral"}`, so the cache breakpoint moves to the newest block each turn |
| `fallbacks` | `"default"` with beta `server-side-fallback-2026-07-01`, except on Haiku 5.5, which has no server-side fallback (`COD_FALLBACKS=0` turns it off) |

### History rules

The history is append-only, which keeps the prompt cache warm and keeps thinking blocks valid.

- Assistant content is echoed back exactly as the API returned it, thinking signatures included.
- After a mid-output fallback, blocks before the last `fallback` marker are reduced to their text; the marker and everything after it are kept.
- A refused, stopped or failed turn is left out of the history, together with the user message that prompted it. The page shows it greyed out so the user can rephrase.

### Event stream (`POST /api/chat`)

| Event | Data |
| :--- | :--- |
| `start` | `{"model"}`: the model serving the turn (it can differ after a sticky fallback) |
| `block` | `{"index", "block"}`: a new content block's type and metadata, without its text |
| `delta` | `{"index", "kind": "text" \| "thinking", "text"}` |
| `done` | `{"model", "stop_reason", "stop_details", "history", "usage"}`: `history` is `null` on a refusal |
| `error` | `{"status", "message"}`: an API status error, a connection error or missing credentials |

Malformed requests are rejected with HTTP 422 before any API call. That covers unknown models or effort levels, a history that doesn't start and end with a user message, empty content, and requests over 8 MB.

### Visual tokens

The page uses a warm, low-contrast palette with a serif for assistant prose, a sans for the interface and a mono for code and usage lines. Dark mode follows the system setting and can be toggled; the choice is remembered in local storage.

| Token | Light | Dark | Use |
| :--- | :--- | :--- | :--- |
| `--bg-canvas` | `#faf9f5` | `#181715` | Page background |
| `--bg-surface-soft` | `#f5f0e8` | `#1f1e1b` | Sidebar, thinking panel |
| `--bg-surface-card` | `#efe9de` | `#252320` | Composer, notices, inline code |
| `--bg-surface-strong` | `#e8e0d2` | `#2f2d29` | User messages, hover |
| `--accent-primary` | `#cc785c` | `#d97757` | Send button, links |
| `--accent-fig` | `#c46686` | `#d97a9a` | Errors and refusals |
| `--border-hairline` | `#d1cfc5` | `#33312d` | 1px borders |

Fonts are Newsreader (prose), Inter (interface) and JetBrains Mono (code), with system fallbacks when Google Fonts can't load.
