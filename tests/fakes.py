"""A fake Anthropic client for tests: replays canned messages as stream events, never touches the network."""
from types import SimpleNamespace

from anthropic.types.beta import BetaMessage


def make_message(content, stop_reason="end_turn", stop_details=None, model="claude-opus-5-5", usage=None):
    return BetaMessage.model_validate({
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": usage or {"input_tokens": 12, "output_tokens": 7, "cache_read_input_tokens": 900},
    })


def tool_use(tool_id, name, tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


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
    """
    Answers each `beta.messages.stream` call with the next canned message (the
    last one repeats). `calls` records a deep copy of every request's params.
    """

    def __init__(self, *messages, error=None):
        self.calls = []
        self._messages = list(messages)
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        import copy

        self.calls.append(copy.deepcopy(params))
        if self._error:
            raise self._error
        message = self._messages.pop(0) if len(self._messages) > 1 else self._messages[0]
        return FakeStream(message)
