# cod.ai

A coding agent for the terminal, plus a local web chat, built on the Claude Messages API with the Anthropic Python SDK.

`cod` gives Claude tools in your project (read, write and edit files, glob, grep, a shell, and a memory folder), asks before it edits or runs anything, and saves every session so you can pick it up later. Long sessions are compacted by the API, so they can keep going past the context window.

## Install

Requires Python 3.11 or newer.

```bash
git clone https://github.com/heretek-ai/cod.ai && cd cod.ai
pip install -e .
```

Credentials are resolved by the SDK: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile. Set `ANTHROPIC_BASE_URL` to send requests through a gateway or a local credential proxy instead.

## Terminal agent

```bash
cd your-project
cod                          # interactive session
cod -p "why does test_login fail?"   # one prompt, answer on stdout
git diff | cod -p -          # prompt from stdin
cod --continue               # resume the latest session in this project
cod --resume 20261025-164712-76741b
```

| Option | Effect |
| :--- | :--- |
| `--model` | `claude-opus-5-5` (default), `claude-fable-5-1`, `claude-sonnet-5-5` or `claude-haiku-5-5` |
| `--effort` | `low` to `max`; defaults to the model's own default |
| `--accept-edits` | Apply file edits without asking (shell commands still ask) |
| `--allow-all` | Run every tool call without asking |
| `--root` | Project directory the tools work in (default: current directory) |
| `--hide-thinking` | Don't request or print thinking summaries |
| `--no-project-files` | Leave `CLAUDE.md` and `AGENTS.md` out of a new session's prompt |
| `--no-fallbacks` | Turn off the server-side refusal fallback |
| `--sandbox auto\|on\|off` | Run shell commands under bubblewrap; `auto` (default) uses it when `bwrap` is installed |
| `--compact-at TOKENS` | Input size at which the API summarizes earlier context (default 150,000) |
| `--no-compact` | Turn off server-side compaction |
| `--no-memory` | Start a session without the memory tool |

In the interactive session, `/help`, `/session`, `/usage` and `/exit` are available, and Ctrl-C stops the current turn. Token usage is printed after each turn.

### Permissions

Reads and searches run freely. Edits and shell commands ask first; answer `y`, `n`, or `a` to allow that tool (edits) or that exact command (shell) for the rest of the session. With no terminal to ask on, as in `cod -p` in a pipeline, anything that would ask is denied.

Standing rules go in `.cod/settings.json` in the project. A rule is a tool name, optionally with a glob matched against the command (for `bash`) or path (for the file tools). `deny` always wins, even over `--allow-all`:

```json
{
  "permissions": {
    "allow": ["bash(git status*)", "bash(pytest*)"],
    "deny": ["bash(rm -rf*)", "read_file(.env*)"]
  }
}
```

All paths are confined to the project root, and the file tools can't write into `.cod/`. Shell commands run with stdin closed and with environment variables whose names look like secrets (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, `*CREDENTIAL*`, `*AUTH*`) removed.

When [bubblewrap](https://github.com/containers/bubblewrap) is installed (`apt install bubblewrap`), shell commands also run in a sandbox: everything outside the project and a private `/tmp` is read-only, your home directory is hidden apart from `~/.gitconfig`, and `.cod/` is read-only. The network stays on. Without bubblewrap the shell runs as you, so treat `--allow-all` as giving Claude your shell; `--sandbox on` refuses to start instead.

### Memory

Claude can keep notes for a project in `.cod/memory/` with the memory tool, and checks them at the start of a task. Memory writes don't ask for approval because they can't leave that folder; a rule such as `"deny": ["memory(delete *)"]` restricts them.

### Sessions

Each session is an append-only JSONL file in `.cod/sessions/` holding the model, the system prompt and every message as sent. A refused turn is dropped from the history so you can rephrase. Add `.cod/sessions/` to your project's `.gitignore`.

## Web chat

```bash
cod serve                    # http://127.0.0.1:8642
cod serve --port 9000
```

A plain chat with streaming, thinking summaries, model and effort selectors and per-reply token usage. It has no tools. The API key stays on the server and the page has no authentication, so `cod serve` binds only loopback addresses unless you pass `--allow-remote`. `COD_PROJECT_CONTEXT=0` leaves this repository's `CLAUDE.md` and `AGENTS.md` out of its system prompt, and `COD_FALLBACKS=0` turns off the refusal fallback. See [DESIGN.md](DESIGN.md) for how requests are built.

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests use a fake Anthropic client and never call the API.

```text
src/
├── cli.py            # `cod` and `cod serve`
├── web_server.py     # FastAPI server for the web chat
├── agent/
│   ├── engine.py     # the tool-use loop
│   ├── tools.py      # file, search and shell tools, bubblewrap sandbox
│   ├── memory_tool.py  # the memory tool, stored in .cod/memory/
│   ├── permissions.py
│   ├── session.py    # JSONL session files
│   ├── prompt.py     # system prompt
│   ├── models.py     # model table and history rules shared with the web chat
│   └── terminal.py   # REPL and print mode
└── agents/
    ├── memory.py     # versioned file memory store
    └── coordinator.py  # runs workers in separate git worktrees
web/index.html        # the web chat page
tests/
```
