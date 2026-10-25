# Agent notes

See `CLAUDE.md` for how to work on this repository; the same rules apply to any coding agent.

The agent itself lives in `src/agent/`. `engine.py` runs the loop and yields events; `terminal.py` and `web.py` are the two front ends that consume them. A new front end should consume `Agent.send()` events too, rather than calling the API itself.
