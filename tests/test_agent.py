"""Tests for the agent (`src/agent/`): tools, permissions, sessions, the tool loop and the CLI, all against a fake client."""
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import anthropic
import httpx2

from fakes import FakeClient, make_message, tool_use
from src import cli
from src.agent import engine
from src.agent.engine import Agent, AgentConfig, ApiError, FallbackNotice, TextDelta, ToolOutput, TurnEnd
from src.agent.permissions import InvalidRuleError, PermissionPolicy, Rule
from src.agent.prompt import build_agent_prompt
from src.agent.session import Session, SessionError
from src.agent.tools import MAX_OUTPUT_CHARS, Toolbox, api_tool_definitions, sanitized_env


class TempProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.toolbox = Toolbox(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class ToolTests(TempProject):
    def test_paths_cannot_escape_the_root(self):
        outside = Path(tempfile.mkdtemp())
        (outside / "secret.txt").write_text("nope", encoding="utf-8")
        (self.root / "link").symlink_to(outside)
        for path in ("../secret.txt", str(outside / "secret.txt"), "link/secret.txt"):
            with self.subTest(path=path):
                result = self.toolbox.run("read_file", {"path": path})
                self.assertTrue(result.is_error)
                self.assertIn("outside the project root", result.content)
        result = self.toolbox.run("write_file", {"path": "../escape.txt", "content": "x"})
        self.assertTrue(result.is_error)
        self.assertFalse((self.root.parent / "escape.txt").exists())
        self.assertTrue(self.toolbox.run("glob", {"pattern": "../*"}).is_error)

    def test_read_file_numbers_lines_and_pages(self):
        self.write("a.txt", "\n".join(f"line {i}" for i in range(1, 11)))
        result = self.toolbox.run("read_file", {"path": "a.txt", "offset": 3, "limit": 2})
        self.assertFalse(result.is_error)
        self.assertEqual(result.content.splitlines()[:2], ["3\tline 3", "4\tline 4"])
        self.assertIn("offset=5", result.content)

    def test_edit_file_requires_a_unique_match(self):
        self.write("a.py", "x = 1\nx = 1\ny = 2\n")
        ambiguous = self.toolbox.run("edit_file", {"path": "a.py", "old_string": "x = 1", "new_string": "x = 3"})
        self.assertTrue(ambiguous.is_error)
        self.assertIn("2 times", ambiguous.content)
        missing = self.toolbox.run("edit_file", {"path": "a.py", "old_string": "z = 9", "new_string": "z = 0"})
        self.assertTrue(missing.is_error)
        self.assertFalse(self.toolbox.run("edit_file", {"path": "a.py", "old_string": "y = 2", "new_string": "y = 5"}).is_error)
        self.assertFalse(self.toolbox.run("edit_file", {"path": "a.py", "old_string": "x = 1", "new_string": "x = 3", "replace_all": True}).is_error)
        self.assertEqual((self.root / "a.py").read_text(), "x = 3\nx = 3\ny = 5\n")

    def test_invalid_inputs_are_tool_errors(self):
        for name, tool_input in [
            ("read_file", {}),
            ("read_file", {"path": "a", "extra": 1}),
            ("bash", {"command": "true", "timeout": 10_000}),
            ("edit_file", {"path": "a", "old_string": "", "new_string": "b"}),
            ("nope", {}),
        ]:
            with self.subTest(name=name, tool_input=tool_input):
                self.assertTrue(self.toolbox.run(name, tool_input).is_error)

    def test_glob_and_grep_skip_ignored_directories(self):
        self.write("src/app.py", "def main():\n    return 'needle'\n")
        self.write("node_modules/dep/index.js", "needle\n")
        self.write(".git/config", "needle\n")
        self.assertEqual(self.toolbox.run("glob", {"pattern": "**/*.py"}).content, "src/app.py")
        grep = self.toolbox.run("grep", {"pattern": "NEEDLE", "ignore_case": True})
        self.assertEqual(grep.content, "src/app.py:2:     return 'needle'")
        self.assertTrue(self.toolbox.run("grep", {"pattern": "("}).is_error)

    def test_bash_runs_in_the_root_without_secrets(self):
        env = {"PATH": os.environ.get("PATH", ""), "ANTHROPIC_API_KEY": "sk-ant-test", "GITHUB_TOKEN": "ghp_x", "SSH_AUTH_SOCK": "/tmp/agent.sock", "LANG": "C"}
        with mock.patch.dict(os.environ, env, clear=True):
            result = self.toolbox.run("bash", {"command": "pwd; env"})
        self.assertFalse(result.is_error)
        self.assertTrue(result.content.startswith("exit code 0\n"))
        self.assertIn(str(self.root), result.content)
        self.assertNotIn("sk-ant-test", result.content)
        self.assertNotIn("ghp_x", result.content)
        self.assertIn("SSH_AUTH_SOCK=/tmp/agent.sock", result.content)
        self.assertNotIn("ANTHROPIC_API_KEY", sanitized_env({"ANTHROPIC_API_KEY": "x", "HOME": "/h"}))

    def test_bash_reports_exit_codes_and_timeouts(self):
        self.assertTrue(self.toolbox.run("bash", {"command": "echo oops >&2; exit 3"}).content.startswith("exit code 3\noops"))
        timed_out = self.toolbox.run("bash", {"command": "sleep 5", "timeout": 1})
        self.assertTrue(timed_out.is_error)
        self.assertIn("timed out", timed_out.content)

    def test_long_output_is_truncated(self):
        self.write("big.txt", "x" * (MAX_OUTPUT_CHARS + 100))
        result = self.toolbox.run("bash", {"command": "cat big.txt"})
        self.assertIn("[truncated", result.content)
        self.assertLess(len(result.content), MAX_OUTPUT_CHARS + 200)

    def test_tool_definitions_stream_eagerly(self):
        tools = api_tool_definitions()
        self.assertEqual([t["name"] for t in tools], ["read_file", "write_file", "edit_file", "glob", "grep", "bash"])
        self.assertTrue(all(t["eager_input_streaming"] for t in tools))
        self.assertTrue(all(t["input_schema"]["additionalProperties"] is False for t in tools))


class PermissionTests(TempProject):
    def test_defaults_by_mode(self):
        default = PermissionPolicy()
        self.assertEqual(default.decide("read_file", "a.py"), "allow")
        self.assertEqual(default.decide("edit_file", "a.py"), "ask")
        self.assertEqual(default.decide("bash", "ls"), "ask")
        self.assertEqual(PermissionPolicy(mode="accept-edits").decide("write_file", "a.py"), "allow")
        self.assertEqual(PermissionPolicy(mode="accept-edits").decide("bash", "ls"), "ask")
        self.assertEqual(PermissionPolicy(mode="allow-all").decide("bash", "ls"), "allow")

    def test_rules_from_settings_and_deny_wins(self):
        self.write(".cod/settings.json", json.dumps({"permissions": {
            "allow": ["bash(git status*)", "bash(rm -rf*)"],
            "deny": ["bash(rm -rf*)", "read_file(.env*)"],
            "ask": ["grep"],
        }}))
        policy = PermissionPolicy.from_settings(self.root, mode="allow-all")
        self.assertEqual(policy.decide("bash", "git status --short"), "allow")
        self.assertEqual(policy.decide("bash", "rm -rf /"), "deny")
        self.assertEqual(policy.decide("read_file", ".env.local"), "deny")
        self.assertEqual(policy.decide("grep", "x"), "allow")
        self.assertEqual(PermissionPolicy.from_settings(self.root).decide("grep", "x"), "ask")

    def test_bad_settings_are_rejected(self):
        with self.assertRaises(InvalidRuleError):
            Rule.parse("shell(ls)")
        self.write(".cod/settings.json", json.dumps({"permissions": {"allow": "bash"}}))
        with self.assertRaises(InvalidRuleError):
            PermissionPolicy.from_settings(self.root)
        self.write(".cod/settings.json", "{not json")
        with self.assertRaises(InvalidRuleError):
            PermissionPolicy.from_settings(self.root)

    def test_session_rules(self):
        policy = PermissionPolicy()
        policy.allow_for_session(Rule("bash", "make test"))
        self.assertEqual(policy.decide("bash", "make test"), "allow")
        self.assertEqual(policy.decide("bash", "make deploy"), "ask")


class SessionTests(TempProject):
    def test_create_append_rollback_and_resume(self):
        session = Session.create(self.root, "claude-opus-5-5", "system text")
        session.append({"role": "user", "content": "one"})
        session.append({"role": "assistant", "content": [{"type": "text", "text": "two"}]})
        session.append({"role": "user", "content": "three"})
        session.rollback(1)
        loaded = Session.find(self.root)
        self.assertEqual(loaded.id, session.id)
        self.assertEqual(loaded.system_prompt, "system text")
        self.assertEqual(loaded.messages, session.messages)
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(Session.find(self.root, session.id).messages, loaded.messages)

    def test_missing_and_corrupt_sessions(self):
        with self.assertRaises(SessionError):
            Session.find(self.root)
        with self.assertRaises(SessionError):
            Session.find(self.root, "nope")
        bad = self.write(".cod/sessions/bad.jsonl", "{broken\n")
        with self.assertRaises(SessionError):
            Session.load(bad)

    def test_system_prompt_includes_project_files(self):
        self.write("CLAUDE.md", "Run make test.")
        prompt = build_agent_prompt(self.root)
        self.assertIn('<project_file name="CLAUDE.md">\nRun make test.\n</project_file>', prompt)
        self.assertIn(f"Project root: {self.root}", prompt)
        self.assertNotIn("project_file", build_agent_prompt(self.root, include_project_files=False))


def scripted_approver(*answers):
    asked = []

    async def approve(name, summary, tool_input):
        asked.append((name, summary))
        return answers[len(asked) - 1]

    approve.asked = asked
    return approve


class EngineTests(TempProject):
    def make_agent(self, client, approver=None, mode="default", **config):
        self.session = Session.create(self.root, "claude-opus-5-5", "SYSTEM")
        policy = PermissionPolicy.from_settings(self.root, mode)
        return Agent(client, self.session, self.toolbox, policy, approver or scripted_approver(), AgentConfig(**config))

    def run_turn(self, agent, prompt="Do it"):
        async def collect():
            return [event async for event in agent.send(prompt)]
        return asyncio.run(collect())

    def test_text_turn_and_request_shape(self):
        client = FakeClient(make_message([
            {"type": "thinking", "thinking": "Hmm.", "signature": "sig"},
            {"type": "text", "text": "Done."},
        ]))
        agent = self.make_agent(client)
        events = self.run_turn(agent, "Hello")
        self.assertEqual("".join(e.text for e in events if isinstance(e, TextDelta)), "Done.")
        self.assertIsInstance(events[-1], TurnEnd)
        self.assertEqual(events[-1].stop_reason, "end_turn")
        self.assertEqual(events[-1].usage["cache_read_input_tokens"], 900)

        params = client.calls[0]
        self.assertEqual(params["model"], "claude-opus-5-5")
        self.assertEqual(params["system"], "SYSTEM")
        self.assertEqual(params["output_config"], {"effort": "medium"})
        self.assertEqual(params["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(params["cache_control"], {"type": "ephemeral"})
        self.assertEqual(params["fallbacks"], "default")
        self.assertEqual(params["tools"], api_tool_definitions())
        self.assertNotIn("tool_choice", params)
        self.assertEqual(params["messages"], [{"role": "user", "content": "Hello"}])

        # The assistant turn is stored verbatim, thinking signature included, and on disk.
        self.assertEqual(self.session.messages[-1]["content"][0], {"type": "thinking", "thinking": "Hmm.", "signature": "sig"})
        self.assertEqual(Session.load(self.session.path).messages, self.session.messages)

    def test_tool_round_trip_keeps_history_append_only(self):
        self.write("notes.txt", "remember the milk\n")
        client = FakeClient(
            make_message([{"type": "text", "text": "Reading."}, tool_use("tu_1", "read_file", {"path": "notes.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "It says milk."}]),
        )
        agent = self.make_agent(client)
        events = self.run_turn(agent)
        self.assertEqual([(e.name, e.summary) for e in events if isinstance(e, engine.ToolCall)], [("read_file", "notes.txt")])
        outputs = [e for e in events if isinstance(e, ToolOutput)]
        self.assertEqual(len(outputs), 1)
        self.assertIn("remember the milk", outputs[0].content)

        first, second = client.calls
        self.assertEqual(second["messages"][: len(first["messages"])], first["messages"])
        result = second["messages"][-1]["content"][0]
        self.assertEqual(result["type"], "tool_result")
        self.assertEqual(result["tool_use_id"], "tu_1")
        self.assertFalse(result["is_error"])
        self.assertEqual(len(self.session.messages), 4)
        # Usage adds up across both requests.
        self.assertEqual(events[-1].usage["input_tokens"], 24)

    def test_approval_denied_always_and_blocked(self):
        self.write(".cod/settings.json", json.dumps({"permissions": {"deny": ["bash(rm *)"]}}))
        approver = scripted_approver("no", "always")
        client = FakeClient(
            make_message([tool_use("t1", "bash", {"command": "echo first"})], stop_reason="tool_use"),
            make_message([tool_use("t2", "bash", {"command": "echo second"})], stop_reason="tool_use"),
            make_message([tool_use("t3", "bash", {"command": "echo second"}), tool_use("t4", "bash", {"command": "rm x"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "ok"}]),
        )
        agent = self.make_agent(client, approver)
        outputs = [e for e in self.run_turn(agent) if isinstance(e, ToolOutput)]
        self.assertEqual([o.outcome for o in outputs], ["denied", "ran", "ran", "blocked"])
        self.assertEqual(outputs[0].content, engine.DENIED_MESSAGE)
        self.assertIn("second", outputs[1].content)
        # "always" covered the repeated command, and the deny rule was never asked about.
        self.assertEqual(approver.asked, [("bash", "echo first"), ("bash", "echo second")])

    def test_always_on_an_edit_allows_all_edits(self):
        self.write("a.txt", "one\n")
        approver = scripted_approver("always", "always")
        client = FakeClient(
            make_message([tool_use("t1", "edit_file", {"path": "a.txt", "old_string": "one", "new_string": "two"})], stop_reason="tool_use"),
            make_message([tool_use("t2", "write_file", {"path": "b.txt", "content": "new"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "ok"}]),
        )
        self.run_turn(self.make_agent(client, approver))
        self.assertEqual(len(approver.asked), 2)  # write_file is a different tool, so it asks once too
        self.assertEqual((self.root / "a.txt").read_text(), "two\n")
        self.assertEqual((self.root / "b.txt").read_text(), "new")

    def test_refusal_rolls_back_the_whole_turn(self):
        self.write("a.txt", "x\n")
        client = FakeClient(
            make_message([{"type": "text", "text": "Earlier answer."}]),
            make_message([tool_use("t1", "read_file", {"path": "a.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "Partial"}], stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber"}),
        )
        agent = self.make_agent(client)
        self.run_turn(agent, "First")
        before = list(self.session.messages)
        events = self.run_turn(agent, "Second")
        self.assertEqual(events[-1].stop_reason, "refusal")
        self.assertEqual(events[-1].refusal_category, "cyber")
        self.assertEqual(self.session.messages, before)
        self.assertEqual(Session.load(self.session.path).messages, before)

    def test_max_tokens_with_a_tool_call_does_not_run_it(self):
        client = FakeClient(
            make_message([tool_use("t1", "write_file", {"path": "big.txt", "content": "cut"})], stop_reason="max_tokens"),
            make_message([{"type": "text", "text": "Retried."}]),
        )
        outputs = [e for e in self.run_turn(self.make_agent(client, mode="allow-all")) if isinstance(e, ToolOutput)]
        self.assertEqual(outputs[0].outcome, "truncated")
        self.assertTrue(outputs[0].is_error)
        self.assertFalse((self.root / "big.txt").exists())

    def test_max_tokens_without_tools_ends_the_turn(self):
        events = self.run_turn(self.make_agent(FakeClient(make_message([{"type": "text", "text": "Cut o"}], stop_reason="max_tokens"))))
        self.assertEqual(events[-1].stop_reason, "max_tokens")

    def test_pause_turn_resends_without_a_new_user_message(self):
        client = FakeClient(
            make_message([{"type": "text", "text": "Part one."}], stop_reason="pause_turn"),
            make_message([{"type": "text", "text": "Part two."}]),
        )
        self.run_turn(self.make_agent(client))
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([m["role"] for m in client.calls[1]["messages"]], ["user", "assistant"])

    def test_tool_rounds_are_capped(self):
        client = FakeClient(make_message([tool_use("t", "glob", {"pattern": "*"})], stop_reason="tool_use"))
        events = self.run_turn(self.make_agent(client, max_tool_rounds=3))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(events[-1].stop_reason, "tool_rounds")
        self.assertEqual(self.session.messages[-1]["content"][0]["type"], "tool_result")

    def test_fallback_history_and_notice(self):
        content = [
            {"type": "thinking", "thinking": "", "signature": "declined"},
            {"type": "text", "text": "Partial."},
            {"type": "fallback", "from": {"model": "claude-opus-5-5"}, "to": {"model": "claude-opus-5"}, "trigger": {"type": "refusal"}},
            {"type": "text", "text": "Finished."},
        ]
        events = self.run_turn(self.make_agent(FakeClient(make_message(content, model="claude-opus-5"))))
        notice = [e for e in events if isinstance(e, FallbackNotice)][0]
        self.assertEqual(notice.to_model, "claude-opus-5")
        self.assertEqual(events[-1].model, "claude-opus-5")
        self.assertEqual(self.session.messages[-1]["content"], content[1:])

    def test_haiku_has_no_fallbacks(self):
        client = FakeClient(make_message([{"type": "text", "text": "ok"}], model="claude-haiku-5-5"))
        self.run_turn(self.make_agent(client, model="claude-haiku-5-5", effort="low"))
        self.assertNotIn("fallbacks", client.calls[0])
        self.assertEqual(client.calls[0]["output_config"], {"effort": "low"})

    def test_api_errors_end_the_turn(self):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx2.Response(529, request=request, json={"error": {"message": "Overloaded"}})
        error = anthropic.APIStatusError("Overloaded", response=response, body={"error": {"message": "Overloaded"}})
        events = self.run_turn(self.make_agent(FakeClient(error=error)))
        self.assertEqual(events, [ApiError(529, "Overloaded")])

    def test_interrupt_answers_open_tool_calls(self):
        client = FakeClient(make_message([
            tool_use("t1", "read_file", {"path": "a.txt"}),
            tool_use("t2", "bash", {"command": "echo hi"}),
        ], stop_reason="tool_use"))
        self.write("a.txt", "x\n")

        async def hang(name, summary, tool_input):
            await asyncio.sleep(3600)

        agent = self.make_agent(client, hang)

        async def interrupted():
            task = asyncio.create_task(self._drain(agent))
            await asyncio.sleep(0.2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(interrupted())
        results = Session.load(self.session.path).messages[-1]["content"]
        self.assertEqual([r["tool_use_id"] for r in results], ["t1", "t2"])
        self.assertFalse(results[0]["is_error"])
        self.assertEqual(results[1]["content"], engine.INTERRUPTED_MESSAGE)

    async def _drain(self, agent):
        async for _ in agent.send("go"):
            pass


class CliTests(TempProject):
    def cod(self, *argv, client, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        code = cli.agent_main(["--root", str(self.root), *argv], client=client, stdin=io.StringIO(stdin), stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()

    def test_print_mode_answers_and_saves_the_session(self):
        client = FakeClient(make_message([{"type": "thinking", "thinking": "Hm.", "signature": "s"}, {"type": "text", "text": "4"}]))
        code, out, err = self.cod("-p", "2+2?", client=client)
        self.assertEqual((code, out), (0, "4\n"))
        self.assertIn("Hm.", err)
        session = Session.find(self.root)
        self.assertEqual(session.messages[0], {"role": "user", "content": "2+2?"})

    def test_print_mode_reads_stdin_and_denies_without_a_terminal(self):
        client = FakeClient(
            make_message([tool_use("t1", "bash", {"command": "touch made.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "Could not."}]),
        )
        code, out, err = self.cod("-p", "-", client=client, stdin="make a file")
        self.assertEqual(code, 0)
        self.assertEqual(client.calls[0]["messages"][0]["content"], "make a file")
        self.assertIn("no terminal to ask on", err)
        self.assertFalse((self.root / "made.txt").exists())

        code, _, _ = self.cod("-p", "again", "--allow-all", client=FakeClient(
            make_message([tool_use("t1", "bash", {"command": "touch made.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "Made."}]),
        ))
        self.assertTrue((self.root / "made.txt").exists())

    def test_continue_resumes_the_latest_session(self):
        self.cod("-p", "first", client=FakeClient(make_message([{"type": "text", "text": "one"}])))
        client = FakeClient(make_message([{"type": "text", "text": "two"}]))
        self.cod("-c", "-p", "second", client=client)
        roles = [(m["role"], m["content"] if isinstance(m["content"], str) else m["content"][0]["text"]) for m in client.calls[0]["messages"]]
        self.assertEqual(roles, [("user", "first"), ("assistant", "one"), ("user", "second")])
        self.assertEqual(len(list((self.root / ".cod" / "sessions").glob("*.jsonl"))), 1)

    def test_exit_codes(self):
        refusal = make_message([], stop_reason="refusal", stop_details={"type": "refusal", "category": None})
        code, _, err = self.cod("-p", "x", client=FakeClient(refusal))
        self.assertEqual(code, 2)
        self.assertIn("declined", err)
        code, _, err = self.cod("-p", "x", client=FakeClient(error=TypeError("Could not resolve authentication method")))
        self.assertEqual(code, 1)
        self.assertIn("authentication", err)
        code, _, err = self.cod("--resume", "missing", "-p", "x", client=FakeClient(refusal))
        self.assertEqual(code, 1)
        self.assertIn("no session file", err)

    def test_serve_refuses_public_hosts(self):
        self.assertTrue(cli.is_loopback_host("::1"))
        self.assertFalse(cli.is_loopback_host("0.0.0.0"))
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            cli.main(["serve", "--host", "0.0.0.0"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
