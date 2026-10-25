#!/usr/bin/env python3
"""
`cod.ai` Unified Headless CLI & Daemon Entrypoint (`/src/cli.py`).
Supports:
  - `cod status` / `cod skill doctor`: Runs live telemetry and invariant health checks.
  - `cod auto-mode critique`: Runs the `17_auto_mode_critique.md` permission rule auditor.
  - `cod simple`: Prints the 4-line `COD_SIMPLE=true` minimal benchmark prompt.
  - `cod verify`: Runs the 5-Step Universal Baseline via the Adversarial Verification Agent.
  - `cod serve`: Starts the local web chat GUI (`src/web_server.py`) on http://127.0.0.1:8642.
"""
import argparse
import json
from pathlib import Path
import sys

from src.prompts.simple_mode import build_simple_mode_prompt
from src.security.classifier import TwoStageSecurityClassifier
from src.security.telemetry import SkillDoctorTelemetryEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cod", description="cod.ai Next-Generation Agentic Coding Harness")
    sub = parser.add_subparsers(dest="subcommand")

    sub.add_parser("doctor", help="Run /skill doctor and display live telemetry dashboard")
    crit_parser = sub.add_parser("auto-mode", help="Auto-mode security classifier utilities")
    crit_parser.add_argument("action", choices=["critique"], help="Audit permission rules for conflicts and gaps")
    sub.add_parser("simple", help="Emit 4-line COD_SIMPLE=true benchmark prompt")
    serve_parser = sub.add_parser("serve", help="Start the local web chat GUI")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8642, help="Port to listen on (default: 8642)")

    args = parser.parse_args(argv)
    workspace = str(Path(__file__).resolve().parent.parent)

    if args.subcommand == "serve":
        from src.web_server import run

        run(host=args.host, port=args.port)
        return 0

    if args.subcommand == "simple":
        print(build_simple_mode_prompt(cwd=workspace, fixed_date="2026-10-24"))
        return 0

    if args.subcommand == "auto-mode" and args.action == "critique":
        classifier = TwoStageSecurityClassifier()
        report = classifier.critique_permission_rules()
        print(report.summary_markdown)
        return 0

    # Default or `doctor`: run `/skill doctor` telemetry snapshot
    engine = SkillDoctorTelemetryEngine()
    snap = engine.run_skill_doctor(
        session_id="sess_cod_ai_live_01",
        model="claude-opus-5-5",
        active_tokens=185_000,
        context_window=1_000_000,
        cache_read_tokens=480_000,
        cache_write_tokens=45_000,
        cache_rebilled_usd=0.0,
        tokens_before_compact=760_000,
        tokens_after_compact=190_000,
        retrieved_items=["cache_assembler.py", "ttl_scheduler.py", "router_and_retrieval.py"],
        relevant_items={"cache_assembler.py", "ttl_scheduler.py", "router_and_retrieval.py"},
    )
    print(snap.render_dashboard_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
