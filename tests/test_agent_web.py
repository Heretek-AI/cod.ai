"""Tests for the web GUI's agent mode (`src/agent/web.py`), against a fake Anthropic client."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import httpx2
import uvicorn
from fastapi.testclient import TestClient

from fakes import FakeClient, make_message, tool_use
from src import web_server
from src.agent.session import Session
from src.agent.web import AgentService, AgentSettings


def sse_events(lines):
    """Yields (event, data) from an iterator of SSE lines."""
    event = None
    for line in lines:
        if line.startswith("event: "):
            event = line[len("event: "):]
        elif line.startswith("data: "):
            yield event, json.loads(line[len("data: "):])


class AgentWebTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self._saved_service = web_server.app.state.agent_service
        web_server.app.state.agent_service = AgentService(AgentSettings(root=self.root, sandbox="off"))
        self.http = TestClient(web_server.app, base_url="http://127.0.0.1:8642", headers={"X-Cod-Token": web_server.API_TOKEN})

    def tearDown(self):
        web_server.app.state.agent_service = self._saved_service
        web_server.app.dependency_overrides.clear()
        self._tmp.cleanup()


    def start(self, fake, **body):
        web_server.app.state.agent_service.client = lambda: fake
        resp = self.http.post("/api/agent/sessions", json=body)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["id"]

    def turn(self, session_id, prompt):
        resp = self.http.post(f"/api/agent/sessions/{session_id}/turns", json={"prompt": prompt})
        self.assertEqual(resp.status_code, 200)
        return list(sse_events(resp.text.splitlines()))

    def test_turn_streams_events_and_saves_the_session(self):
        (self.root / "a.txt").write_text("hello\n", encoding="utf-8")
        fake = FakeClient(
            make_message([{"type": "text", "text": "Reading."}, tool_use("t1", "read_file", {"path": "a.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "It says hello."}]),
        )
        session_id = self.start(fake, effort="high")
        events = self.turn(session_id, "What's in a.txt?")
        names = [e for e, _ in events]
        self.assertEqual(names[0], "start")
        self.assertIn("tool_call", names)
        self.assertEqual(names[-1], "done")
        output = [d for e, d in events if e == "tool_output"][0]
        self.assertIn("hello", output["content"])
        self.assertEqual(fake.calls[0]["output_config"], {"effort": "high"})
        session = Session.find(self.root, session_id)
        self.assertEqual(session.messages[0], {"role": "user", "content": "What's in a.txt?"})
        self.assertEqual(len(session.messages), 4)

    def live_server(self):
        """Runs the app on a real port: TestClient buffers whole responses, so it can't answer mid-stream."""
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(web_server.app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.02)
        self.addCleanup(thread.join, 5)
        self.addCleanup(setattr, server, "should_exit", True)
        return httpx2.Client(base_url=f"http://127.0.0.1:{port}", headers={"X-Cod-Token": web_server.API_TOKEN}, timeout=10)

    def test_approvals_come_from_the_browser(self):
        fake = FakeClient(
            make_message([tool_use("t1", "write_file", {"path": "new.txt", "content": "made"})], stop_reason="tool_use"),
            make_message([tool_use("t2", "bash", {"command": "rm -f new.txt"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "Done."}]),
        )
        session_id = self.start(fake)
        answers = iter(["yes", "no"])
        approvals = []
        events = []
        with self.live_server() as http:
            with http.stream("POST", f"/api/agent/sessions/{session_id}/turns", json={"prompt": "Make a file"}) as resp:
                self.assertEqual(resp.status_code, 200)
                for event, data in sse_events(resp.iter_lines()):
                    events.append((event, data))
                    if event == "approval":
                        approvals.append(data)
                        answered = http.post(f"/api/agent/sessions/{session_id}/approvals/{data['id']}", json={"answer": next(answers)})
                        self.assertEqual(answered.status_code, 200)
        self.assertEqual([a["name"] for a in approvals], ["write_file", "bash"])
        self.assertEqual(approvals[0]["details"]["preview"], "made")
        outcomes = [d["outcome"] for e, d in events if e == "tool_output"]
        self.assertEqual(outcomes, ["ran", "denied"])
        self.assertEqual((self.root / "new.txt").read_text(), "made")
        # Answering twice, or an unknown id, is a 404.
        self.assertEqual(self.http.post(f"/api/agent/sessions/{session_id}/approvals/{approvals[0]['id']}", json={"answer": "yes"}).status_code, 404)

    def test_closing_the_stream_stops_the_turn(self):
        fake = FakeClient(make_message([tool_use("t1", "bash", {"command": "touch never.txt"})], stop_reason="tool_use"))
        session_id = self.start(fake)
        with self.live_server() as http:
            with http.stream("POST", f"/api/agent/sessions/{session_id}/turns", json={"prompt": "go"}) as resp:
                for event, _ in sse_events(resp.iter_lines()):
                    if event == "approval":
                        break
            live = web_server.app.state.agent_service.live[session_id]
            deadline = time.time() + 5
            while live.busy and time.time() < deadline:
                time.sleep(0.02)
        self.assertFalse(live.busy)
        self.assertFalse((self.root / "never.txt").exists())
        last = Session.find(self.root, session_id).messages[-1]["content"][0]
        self.assertEqual((last["type"], last["tool_use_id"], last["is_error"]), ("tool_result", "t1", True))

    def test_accept_edits_mode_skips_edit_approvals(self):
        fake = FakeClient(
            make_message([tool_use("t1", "write_file", {"path": "x.txt", "content": "x"})], stop_reason="tool_use"),
            make_message([{"type": "text", "text": "ok"}]),
        )
        session_id = self.start(fake, mode="accept-edits")
        events = self.turn(session_id, "go")
        self.assertNotIn("approval", [e for e, _ in events])
        self.assertTrue((self.root / "x.txt").exists())

    def test_sessions_resume_after_a_restart(self):
        fake = FakeClient(make_message([{"type": "text", "text": "one"}]))
        session_id = self.start(fake)
        self.turn(session_id, "first")
        web_server.app.state.agent_service = AgentService(AgentSettings(root=self.root, sandbox="off"))
        fake2 = FakeClient(make_message([{"type": "text", "text": "two"}]))
        web_server.app.state.agent_service.client = lambda: fake2
        self.turn(session_id, "second")
        self.assertEqual([m["role"] for m in fake2.calls[0]["messages"]], ["user", "assistant", "user"])

    def test_bad_requests(self):
        fake = FakeClient(make_message([{"type": "text", "text": "ok"}]))
        self.assertEqual(self.http.post("/api/agent/sessions", json={"model": "gpt-4o"}).status_code, 422)
        self.assertEqual(self.http.post("/api/agent/sessions", json={"mode": "allow-all"}).status_code, 422)
        self.assertEqual(self.http.post("/api/agent/sessions/../../etc/turns", json={"prompt": "x"}).status_code, 404)
        self.assertEqual(self.http.post("/api/agent/sessions/20260101-000000-abcdef/turns", json={"prompt": "x"}).status_code, 404)
        session_id = self.start(fake)
        self.assertEqual(self.http.post(f"/api/agent/sessions/{session_id}/turns", json={"prompt": ""}).status_code, 422)
        no_token = TestClient(web_server.app, base_url="http://127.0.0.1:8642")
        self.assertEqual(no_token.post(f"/api/agent/sessions/{session_id}/turns", json={"prompt": "x"}).status_code, 403)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
