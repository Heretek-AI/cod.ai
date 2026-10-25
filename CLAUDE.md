# Notes for working on cod.ai

- Python 3.11+, Anthropic Python SDK. Run the tests with `python3 -m unittest discover -s tests`. They use the fake client in `tests/fakes.py`; never make real API calls from tests.
- Requests use adaptive thinking, `output_config.effort`, top-level `cache_control`, and `fallbacks: "default"` where the model supports it (not Haiku 5.5). Don't add `budget_tokens`, `thinking: disabled` or a forced `tool_choice`: the current models reject them.
- The history is append-only. Store assistant content exactly as returned (thinking signatures included), apply `history_content` after a fallback, and keep the system prompt and tool list fixed for a session, or the prompt cache and thinking blocks break.
- Tool inputs come from the model: validate them (the pydantic models in `src/agent/tools.py`) and return failures as `is_error` tool results.
- Credentials stay out of the browser and out of the agent's shell environment (`sanitized_env`).
- `src/agent/models.py` is the one model table; the CLI and the web server both read it.
