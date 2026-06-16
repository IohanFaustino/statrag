"""OllamaAgent — the tool-calling loop that makes Ollama act like a subagent.

The model decides every step via native function-calling; this loop only
executes the tool calls it emits and feeds results back, until the model stops
calling tools (it's done) or ``max_steps`` is hit. Mirrors how a Claude subagent
reads files, writes code, and runs tests autonomously.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tools.ollama_agents import tools as _tools
from tools.ollama_agents.backend import chat

DEFAULT_SYSTEM = """You are an autonomous software-implementer agent working in a git workspace.
You act ONLY by calling the provided tools (read_file, write_file, edit_file, run).
Follow Test-Driven Development: write or inspect the failing test first, run it to
see it FAIL, implement the minimal code, run it again to see it PASS. Use edit_file
for surgical changes ('old' must be unique). Use run for shell/pytest. When the task's
acceptance check passes, STOP calling tools and reply with a short final summary that
starts with 'DONE:' (or 'BLOCKED:' if you cannot proceed). Do not ask for confirmation."""


@dataclass
class AgentResult:
    status: str                       # DONE / BLOCKED / MAX_STEPS
    final_text: str
    steps: int
    transcript: list[dict] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)   # names, in order


class OllamaAgent:
    def __init__(self, model: str, root: str | Path,
                 system_prompt: str = DEFAULT_SYSTEM):
        self.model = model
        self.root = Path(root)
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    def run(self, task: str, max_steps: int = 30) -> AgentResult:
        self.messages.append({"role": "user", "content": task})
        called: list[str] = []
        for step in range(1, max_steps + 1):
            msg = chat(self.model, self.messages, _tools.TOOL_SCHEMAS)
            self.messages.append(_clean_assistant(msg))
            tcs = msg.get("tool_calls") or []
            if not tcs:
                text = msg.get("content") or ""
                status = "BLOCKED" if text.strip().upper().startswith("BLOCKED") else "DONE"
                return AgentResult(status, text, step, self.messages, called)
            for tc in tcs:
                fn = tc["function"]
                name = fn["name"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                called.append(name)
                result = _tools.dispatch(name, args, self.root)
                self.messages.append({"role": "tool", "content": result})
        return AgentResult("MAX_STEPS", "step budget exhausted", max_steps,
                           self.messages, called)


def _clean_assistant(msg: dict) -> dict:
    """Keep only fields the API accepts on a round-trip assistant message."""
    out: dict = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out
