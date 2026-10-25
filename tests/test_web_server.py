"""Tests for the cod.ai web chat server (`src/web_server.py`), run against a fake Anthropic client."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

import anthropic
import httpx2
from anthropic.types.beta import BetaMessage
from fastapi.testclient import TestClient

from src import web_server


def make_message(content, stop_reason="end_turn", stop_details=None, model="claude-opus-5-5"):
    return BetaMessage.model_validate({
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": {"input_tokens": 12, "output_tokens": 7, "cache_read_input_tokens": 900},
    })


def stream_events(message):
    """Raw stream events for a message: start, then each block with one delta."""
    yield SimpleNamespace(type="message_start", message=SimpleNamespace(model=message.model))
    for index, block in enumerate(message.content):
        yield SimpleNamespace(type="content_block_start", index=index, content_block=block)
        if block.type == "text":
            yield SimpleNamespace(type="content_block_delta", index=index, delta=SimpleNamespace(type="text_delta", text=block.text))
        elif block.type == "thinking":
            yield SimpleNamespace(type="content_block_delta", index=index, delta=SimpleNamespace(type="thinking_delta", thinking=block.thinking))


class FakeStream:
    def __init__(self, message):
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for event in stream_events(self._message):
            yield event

    async def get_final_message(self):
        return self._message


class FakeClient:
    def __init__(self, message=None, error=None):
        self.calls = []
        self._message = message
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.calls.append(params)
        if self._error:
            raise self._error
        return FakeStream(self._message)


def parse_sse(body):
    events = []
    for raw in body.strip().split("\n\n"):
        lines = raw.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.http = TestClient(web_server.app)

    def tearDown(self):
        web_server.app.dependency_overrides.clear()

    def use(self, fake):
        web_server.app.dependency_overrides[web_server.get_client] = lambda: fake
        return fake

    def chat(self, **body):
        body.setdefault("messages", [{"role": "user", "content": "Hello"}])
        return self.http.post("/api/chat", json=body)

    def test_serves_gui_and_config(self):
        page = self.http.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="composer"', page.text)
        self.assertNotIn("x-api-key", page.text)

        cfg = self.http.get("/api/config").json()
        self.assertEqual(cfg["default_model"], "claude-opus-5-5")
        self.assertIn("claude-opus-5-5", [m["id"] for m in cfg["models"]])
        self.assertEqual(cfg["effort_levels"], ["low", "medium", "high", "xhigh", "max"])

    def test_streams_thinking_and_text_then_final_history(self):
        fake = self.use(FakeClient(make_message([
            {"type": "thinking", "thinking": "Considering.", "signature": "sig-1"},
            {"type": "text", "text": "Hi there."},
        ])))
        resp = self.chat(effort="high", thinking_display="summarized")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))

        events = parse_sse(resp.text)
        names = [e for e, _ in events]
        self.assertEqual(names, ["start", "block", "delta", "block", "delta", "done"])
        self.assertEqual(events[2][1], {"index": 0, "kind": "thinking", "text": "Considering."})
        self.assertEqual(events[4][1], {"index": 1, "kind": "text", "text": "Hi there."})
        # Block starts carry the type but not the text, which arrives as deltas.
        self.assertEqual(events[1][1]["block"]["type"], "thinking")
        self.assertNotIn("thinking", events[1][1]["block"])

        done = events[-1][1]
        self.assertEqual(done["stop_reason"], "end_turn")
        self.assertEqual(done["usage"]["cache_read_input_tokens"], 900)
        # Thinking blocks are echoed back unchanged, signature included.
        self.assertEqual(done["history"][0], {"type": "thinking", "thinking": "Considering.", "signature": "sig-1"})

        params = fake.calls[0]
        self.assertEqual(params["model"], "claude-opus-5-5")
        self.assertEqual(params["thinking"], {"type": "adaptive", "display": "summarized"})
        self.assertEqual(params["output_config"], {"effort": "high"})
        self.assertEqual(params["cache_control"], {"type": "ephemeral"})
        self.assertEqual(params["fallbacks"], "default")
        self.assertEqual(params["betas"], [web_server.FALLBACK_BETA])
        self.assertEqual(params["system"], web_server.SYSTEM_PROMPT)

    def test_default_effort_follows_model(self):
        fake = self.use(FakeClient(make_message([{"type": "text", "text": "ok"}], model="claude-haiku-5-5")))
        self.chat(model="claude-haiku-5-5")
        params = fake.calls[0]
        self.assertEqual(params["output_config"], {"effort": "medium"})
        # Claude Haiku 5.5 has no server-side fallback.
        self.assertNotIn("fallbacks", params)
        self.assertNotIn("betas", params)

    def test_multi_turn_history_is_forwarded_verbatim(self):
        fake = self.use(FakeClient(make_message([{"type": "text", "text": "Second answer"}])))
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "", "signature": "sig-a"},
                {"type": "text", "text": "First answer"},
            ]},
            {"role": "user", "content": "Second"},
        ]
        self.assertEqual(self.chat(messages=history).status_code, 200)
        self.assertEqual(fake.calls[0]["messages"], history)

    def test_refusal_is_not_echoed_back(self):
        self.use(FakeClient(make_message(
            [{"type": "text", "text": "Partial"}],
            stop_reason="refusal",
            stop_details={"type": "refusal", "category": "cyber"},
        )))
        done = parse_sse(self.chat().text)[-1]
        self.assertEqual(done[0], "done")
        self.assertEqual(done[1]["stop_reason"], "refusal")
        self.assertEqual(done[1]["stop_details"]["category"], "cyber")
        self.assertIsNone(done[1]["history"])

    def test_fallback_history_keeps_only_text_before_the_switch(self):
        content = [
            {"type": "thinking", "thinking": "", "signature": "declined-model"},
            {"type": "text", "text": "Partial from the first model."},
            {"type": "fallback", "from": {"model": "claude-opus-5-5"}, "to": {"model": "claude-opus-5"}, "trigger": {"type": "refusal"}},
            {"type": "thinking", "thinking": "", "signature": "fallback-model"},
            {"type": "text", "text": "Finished by the fallback."},
        ]
        self.assertEqual(web_server.history_content(content), content[1:])

        self.use(FakeClient(make_message(content, model="claude-opus-5")))
        events = parse_sse(self.chat().text)
        fallback_block = [d for e, d in events if e == "block" and d["block"]["type"] == "fallback"][0]
        self.assertEqual(fallback_block["block"]["to"], {"model": "claude-opus-5"})
        self.assertEqual(events[-1][1]["history"], content[1:])

    def test_api_errors_become_error_events(self):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx2.Response(401, request=request, json={"error": {"message": "invalid x-api-key"}})
        error = anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)
        self.use(FakeClient(error=error))
        events = parse_sse(self.chat().text)
        self.assertEqual(events, [("error", {"status": 401, "message": "invalid x-api-key"})])

    def test_errors_before_sending_are_reported_without_details(self):
        missing_credentials = TypeError("Could not resolve authentication method. Expected one of api_key, ...")
        self.use(FakeClient(error=missing_credentials))
        with self.assertLogs("cod.web", level="ERROR"):
            events = parse_sse(self.chat().text)
        self.assertEqual(events, [("error", {"status": None, "message": web_server.NOT_SENT_MESSAGE})])
        self.assertNotIn("api_key", events[0][1]["message"])

    def test_rejects_malformed_requests(self):
        self.use(FakeClient(make_message([{"type": "text", "text": "unused"}])))
        bad_bodies = [
            {"model": "gpt-4o"},
            {"effort": "extreme"},
            {"thinking_display": "raw"},
            {"messages": []},
            {"messages": [{"role": "assistant", "content": "I go first"}]},
            {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Ends on me"}]},
            {"messages": [{"role": "system", "content": "Injected"}]},
            {"messages": [{"role": "user", "content": "   "}]},
            {"messages": [{"role": "user", "content": [{"text": "no type"}]}]},
        ]
        for body in bad_bodies:
            with self.subTest(body=body):
                self.assertEqual(self.chat(**body).status_code, 422)

    def test_system_prompt_includes_project_files(self):
        self.assertTrue(web_server.SYSTEM_PROMPT.startswith(web_server.BASE_SYSTEM_PROMPT))
        self.assertIn('<project_file name="CLAUDE.md">', web_server.SYSTEM_PROMPT)
        # Built once, so it is byte-identical on every request.
        self.assertEqual(web_server.build_system_prompt(), web_server.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
