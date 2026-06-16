"""Battery 3 — LIVE end-to-end against real Ollama cloud (costs tokens).

Gated by env OLLAMA_LIVE=1 so default test runs don't spend money. This is the
parity proof: an Ollama agent, given a TDD task in a scratch workspace,
reproduces step-by-step what a Claude subagent would do — read/write files, run
pytest, and finish with the tests passing.

Run:  OLLAMA_LIVE=1 .venv/bin/python -m pytest tools/ollama_agents/tests/test_live.py -q -s
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from tools.ollama_agents.delegate import MODELS, delegate

LIVE = os.environ.get("OLLAMA_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="set OLLAMA_LIVE=1 to run (spends tokens)")

MODEL = os.environ.get("OLLAMA_LIVE_MODEL", "qwen3-coder-next")


def test_live_tdd_task_reaches_green(tmp_path):
    pyexe = sys.executable  # this box has no bare `python`; pin the venv interpreter
    task = (
        "In this workspace create two files. "
        "1) test_calc.py containing:\n"
        "from calc import add\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "    assert add(-1, 1) == 0\n"
        "2) calc.py implementing add(a, b). "
        f"Then run: {pyexe} -m pytest test_calc.py -q  and ensure it passes. "
        "When green, reply DONE."
    )
    res = delegate(task, model=MODEL, root=str(tmp_path), max_steps=20)
    print(f"\nstatus={res.status} steps={res.steps} tools={res.tool_calls}")
    print(res.final_text)

    # Parity assertions: it actually used tools, wrote both files, and pytest is green.
    assert "write_file" in res.tool_calls
    assert "run" in res.tool_calls
    assert (tmp_path / "calc.py").exists()
    assert (tmp_path / "test_calc.py").exists()
    from tools.ollama_agents import tools as T
    out = T.run(tmp_path, f"{pyexe} -m pytest test_calc.py -q")
    assert "[exit 0]" in out


def test_models_rotation_listed():
    # Guard: the rotation pool the user asked for (beyond deepseek/kimi) is present.
    assert "qwen3-coder-next" in MODELS
    assert "glm-5.1" in MODELS
    assert len(MODELS) >= 4
