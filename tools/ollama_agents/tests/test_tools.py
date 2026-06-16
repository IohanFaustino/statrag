"""Battery 1 — tool primitives (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from tools.ollama_agents import tools


def test_write_then_read(tmp_path):
    assert "wrote" in tools.write_file(tmp_path, "a/b.txt", "hello")
    assert tools.read_file(tmp_path, "a/b.txt") == "hello"


def test_edit_unique(tmp_path):
    tools.write_file(tmp_path, "f.py", "x = 1\ny = 2\n")
    tools.edit_file(tmp_path, "f.py", "y = 2", "y = 3")
    assert tools.read_file(tmp_path, "f.py") == "x = 1\ny = 3\n"


def test_edit_missing_raises(tmp_path):
    tools.write_file(tmp_path, "f.py", "x = 1\n")
    with pytest.raises(ValueError, match="not found"):
        tools.edit_file(tmp_path, "f.py", "nope", "z")


def test_edit_ambiguous_raises(tmp_path):
    tools.write_file(tmp_path, "f.py", "a\na\n")
    with pytest.raises(ValueError, match="unique"):
        tools.edit_file(tmp_path, "f.py", "a", "b")


def test_run_returns_exit_and_output(tmp_path):
    out = tools.run(tmp_path, "echo hi && exit 3")
    assert "hi" in out and "[exit 3]" in out


def test_path_escape_blocked(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        tools.write_file(tmp_path, "../evil.txt", "x")


def test_dispatch_unknown_tool(tmp_path):
    assert "unknown tool" in tools.dispatch("nope", {}, tmp_path)


def test_dispatch_surfaces_error_as_text(tmp_path):
    # missing file -> error string, not exception
    res = tools.dispatch("read_file", {"path": "missing.txt"}, tmp_path)
    assert res.startswith("ERROR:")
