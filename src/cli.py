#!/usr/bin/env python3
"""
Command line entry point (`src/cli.py`).

    cod                      interactive session in the current directory
    cod -p "prompt"          answer one prompt and exit (`-p -` reads stdin)
    cod --continue           resume the most recent session
    cod --resume <id>        resume a session by id
    cod serve                start the local web chat on http://127.0.0.1:8642
"""
import argparse
import ipaddress
from pathlib import Path
import sys

from src.agent.models import DEFAULT_COMPACT_AT, DEFAULT_MODEL, EFFORT_LEVELS, MODELS


def is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="cod serve", description="Start the local web chat GUI.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8642, help="Port to listen on (default: 8642)")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help=(
            "Allow binding a non-loopback address. The API is guarded only by a token embedded in the page, "
            "so anyone who can load the page can use your credentials and, in agent mode, your files."
        ),
    )
    parser.add_argument("--root", default=".", help="Project the agent mode works in (default: the current directory).")
    parser.add_argument("--sandbox", choices=["auto", "on", "off"], default="auto", help="Shell sandbox for agent mode (default: auto).")
    args = parser.parse_args(argv)
    if not args.allow_remote and not is_loopback_host(args.host):
        parser.error(f"--host {args.host} is not a loopback address; the chat API has no authentication. Pass --allow-remote to bind it anyway.")
    if not Path(args.root).is_dir():
        parser.error(f"--root {args.root} is not a directory")
    from src.web_server import run

    run(host=args.host, port=args.port, root=args.root, sandbox=args.sandbox, allow_remote=args.allow_remote)
    return 0


def agent_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cod",
        description="A coding agent on the Claude Messages API. Run `cod serve` for the web chat.",
    )
    parser.add_argument("-p", "--print", dest="prompt", metavar="PROMPT", help="Answer one prompt and exit; `-` reads it from stdin.")
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument("-c", "--continue", dest="resume_latest", action="store_true", help="Resume the most recent session.")
    resume.add_argument("-r", "--resume", metavar="ID", help="Resume a session by id.")
    parser.add_argument("--model", choices=list(MODELS), help=f"Model to use (default: {DEFAULT_MODEL}, or the resumed session's).")
    parser.add_argument("--effort", choices=EFFORT_LEVELS, help="Effort level (default: the model's own default).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--accept-edits", action="store_true", help="Apply file edits without asking.")
    mode.add_argument("--allow-all", action="store_true", help="Run every tool call without asking, shell commands included.")
    parser.add_argument("--root", default=".", help="Project root the tools work in (default: the current directory).")
    parser.add_argument("--hide-thinking", action="store_true", help="Don't print Claude's thinking summaries.")
    parser.add_argument("--no-project-files", action="store_true", help="Leave CLAUDE.md and AGENTS.md out of a new session's system prompt.")
    parser.add_argument("--no-fallbacks", action="store_true", help="Turn off the server-side refusal fallback.")
    parser.add_argument("--no-memory", action="store_true", help="Start a session without the memory tool (.cod/memory/).")
    parser.add_argument("--no-explore", action="store_true", help="Start a session without the read-only explore sub-agent.")
    parser.add_argument(
        "--sandbox", choices=["auto", "on", "off"], default="auto",
        help="Run shell commands under bubblewrap: auto uses it when installed, on requires it (default: auto).",
    )
    compact = parser.add_mutually_exclusive_group()
    compact.add_argument(
        "--compact-at", type=int, metavar="TOKENS", default=DEFAULT_COMPACT_AT,
        help=f"Input size at which the API summarizes earlier context (default: {DEFAULT_COMPACT_AT:,}).",
    )
    compact.add_argument("--no-compact", action="store_true", help="Turn off server-side compaction.")
    return parser


def agent_main(argv: list[str], client=None, stdin=None, stdout=None, stderr=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = agent_parser()
    args = parser.parse_args(argv)

    from src.agent.engine import Agent, AgentConfig
    from src.agent.permissions import InvalidRuleError, PermissionPolicy
    from src.agent.prompt import build_agent_prompt
    from src.agent.session import Session, SessionError
    from src.agent import terminal
    from src.agent.tools import ToolError, Toolbox

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"--root {args.root} is not a directory")

    prompt = args.prompt
    if prompt == "-":
        prompt = stdin.read()
    if prompt is not None and not prompt.strip():
        parser.error("the prompt is empty")

    try:
        if args.resume_latest or args.resume:
            session = Session.find(root, args.resume)
        else:
            system_prompt = build_agent_prompt(root, include_project_files=not args.no_project_files)
            session = Session.create(
                root, args.model or DEFAULT_MODEL, system_prompt,
                memory_tool=not args.no_memory, explore_tool=not args.no_explore,
            )
        mode = "allow-all" if args.allow_all else "accept-edits" if args.accept_edits else "default"
        policy = PermissionPolicy.from_settings(root, mode)
        toolbox = Toolbox(root, sandbox=args.sandbox, memory=session.memory_tool)
    except (SessionError, InvalidRuleError, ToolError) as exc:
        stderr.write(f"cod: {exc}\n")
        return 1

    interactive = terminal.is_interactive(stdin)
    style = terminal.Style(enabled=terminal.is_interactive(stderr))
    if interactive:
        approver = terminal.make_terminal_approver(input, stderr, style)
    else:
        approver = terminal.make_deny_approver(stderr, style)

    if client is None:
        import anthropic

        client = anthropic.AsyncAnthropic()

    config = AgentConfig(
        model=args.model or session.model,
        effort=args.effort,
        thinking_display="omitted" if args.hide_thinking else "summarized",
        fallbacks=not args.no_fallbacks,
        compact_at=None if args.no_compact else args.compact_at,
    )
    agent = Agent(client, session, toolbox, policy, approver, config)

    if prompt is not None:
        renderer = terminal.Renderer(stdout, stderr, style, show_thinking=not args.hide_thinking)
        return terminal.run_print(agent, prompt, renderer)

    if not interactive:
        parser.error("no prompt given and stdin is not a terminal; pass one with -p")
    renderer = terminal.Renderer(stdout, stdout, style, show_thinking=not args.hide_thinking)
    return terminal.run_repl(agent, renderer)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "serve":
        return serve_main(argv[1:])
    return agent_main(argv)


if __name__ == "__main__":
    sys.exit(main())
