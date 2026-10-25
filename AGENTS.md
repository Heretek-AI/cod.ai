# Agent notes

See `CLAUDE.md` for how to work on this repository; the same rules apply to any coding agent.

The agent itself lives in `src/agent/`. `engine.py` runs the loop and yields events; `terminal.py` renders them. A new front end (such as the web chat) should consume `Agent.send()` events rather than calling the API itself.
