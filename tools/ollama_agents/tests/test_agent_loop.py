"""Battery 2 — the tool-calling loop (mocked backend, no network).

Proves the loop executes the model's tool calls in order, feeds results back,
and stops with the right status — i.e. it reproduces a subagent's step-by-step
read -> write -> run -> done without any real Ollama call.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.ollama_agents import agent as agent_mod
from tools.ollama_agents.agent import OllamaAgent


def _tc(name, args):
    return {"function": {"name": name, "arguments": args}}


def test_loop_executes_tools_in_order_then_done(tmp_path):
    # Scripted model: write a file, run it, then finish.
    scripted = [
        {"tool_calls": [_tc("write_file", {"path": "hi.txt", "content": "hello"})]},
        {"tool_calls": [_tc("run", {"cmd": "cat hi.txt"})]},
        {"content": "DONE: created and verified hi.txt"},
    ]
    calls = iter(scripted)
    with patch.object(agent_mod, "chat", side_effect=lambda *a, **k: next(calls)):
        res = OllamaAgent("fake-model", tmp_path).run("make hi.txt", max_steps=10)

    assert res.status == "DONE"
    assert res.tool_calls == ["write_file", "run"]
    assert (tmp_path / "hi.txt").read_text() == "hello"
    assert res.steps == 3


def test_loop_handles_string_arguments(tmp_path):
    # Some models return arguments as a JSON string, not an object.
    scripted = [
        {"tool_calls": [_tc("write_file", '{"path": "a.txt", "content": "x"}')]},
        {"content": "DONE"},
    ]
    calls = iter(scripted)
    with patch.object(agent_mod, "chat", side_effect=lambda *a, **k: next(calls)):
        res = OllamaAgent("fake", tmp_path).run("t", max_steps=5)
    assert (tmp_path / "a.txt").read_text() == "x"
    assert res.status == "DONE"


def test_loop_blocked_status(tmp_path):
    calls = iter([{"content": "BLOCKED: cannot find the spec"}])
    with patch.object(agent_mod, "chat", side_effect=lambda *a, **k: next(calls)):
        res = OllamaAgent("fake", tmp_path).run("t", max_steps=5)
    assert res.status == "BLOCKED"


def test_loop_respects_max_steps(tmp_path):
    # Model never stops calling tools -> MAX_STEPS guard fires.
    forever = {"tool_calls": [_tc("run", {"cmd": "true"})]}
    with patch.object(agent_mod, "chat", side_effect=lambda *a, **k: dict(forever)):
        res = OllamaAgent("fake", tmp_path).run("t", max_steps=4)
    assert res.status == "MAX_STEPS"
    assert res.steps == 4
