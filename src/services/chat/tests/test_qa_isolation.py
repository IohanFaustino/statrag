"""Hard isolation + dispatch regression tests for the Q&A mode.

Two concerns:
1. Isolation — qa.py, prompts/qa.py, and research.py must NOT import any tutor
   module (deep_tutor, orchestrator_workers, ow_deepagents, ow_skills).
   Additionally qa.py must not import extension_agents (only the shared
   research.py is allowed).

   Implementation uses ``ast`` to walk only Import/ImportFrom nodes in each
   file — comment-immune. A naive substring grep would false-positive on the
   research.py docstring which explicitly mentions the forbidden names.

2. Dispatch regression — mode "qa" still routes to ``agents.qa.run_qa`` via
   ``_V2_DISPATCH`` in ``router.py``.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import get_args

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKTREE = Path(__file__).resolve().parents[4]  # .../qa-story-wiki


def _collect_import_modules(path: Path) -> list[str]:
    """Parse *path* with ast and return every module string that appears in an
    Import or ImportFrom statement.

    Only actual import nodes are visited — comments, docstrings, and string
    literals are ignored entirely, making this check comment-immune.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for bare ``from . import x``
            if node.module:
                modules.append(node.module)
    return modules


# ---------------------------------------------------------------------------
# Files under test
# ---------------------------------------------------------------------------

_QA_AGENT = _WORKTREE / "src/services/chat/agents/qa.py"
_QA_PROMPTS = _WORKTREE / "src/services/chat/prompts/qa.py"
_RESEARCH = _WORKTREE / "src/services/chat/research.py"

# Tokens that must not appear as import module prefixes / substrings
_FORBIDDEN_TUTOR_TOKENS = [
    "deep_tutor",
    "orchestrator_workers",
    "ow_deepagents",
    "ow_skills",
]

# Extension runner must also stay out of qa.py (shared research.py is fine)
_FORBIDDEN_EXTENSION_TOKENS = ["extension_agents"]


# ---------------------------------------------------------------------------
# Isolation tests (ast-based, comment-immune)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_path", [_QA_AGENT, _QA_PROMPTS, _RESEARCH])
def test_no_tutor_imports(source_path: Path):
    """None of qa.py / prompts/qa.py / research.py may import a tutor module.

    Uses ast — so the docstring in research.py that literally mentions the
    forbidden names does NOT trigger a false positive.
    """
    modules = _collect_import_modules(source_path)
    violations = [
        m
        for m in modules
        if any(tok in m for tok in _FORBIDDEN_TUTOR_TOKENS)
    ]
    assert violations == [], (
        f"{source_path.name}: found forbidden tutor imports {violations!r}. "
        "Q&A must remain fully isolated from the tutor pipeline."
    )


def test_qa_agent_no_extension_agents_import():
    """qa.py must not import extension_agents — only the shared research.py is allowed."""
    modules = _collect_import_modules(_QA_AGENT)
    violations = [
        m
        for m in modules
        if any(tok in m for tok in _FORBIDDEN_EXTENSION_TOKENS)
    ]
    assert violations == [], (
        f"qa.py: found extension_agents imports {violations!r}. "
        "Q&A must not import the Extension runner/graph directly."
    )


# ---------------------------------------------------------------------------
# Dispatch regression: mode "qa" → run_qa
# ---------------------------------------------------------------------------


def test_qa_chatrequest_validates():
    """ChatRequest(mode='qa') must pass Pydantic validation."""
    from src.services.chat.schemas._core import ChatRequest

    req = ChatRequest(message="What is heteroskedasticity?", mode="qa")
    assert req.mode == "qa"


def test_v2_dispatch_maps_qa_to_run_qa():
    """_V2_DISPATCH['qa'] must be the function that delegates to agents.qa.run_qa.

    The router wraps run_qa in a thin ``_run_qa`` shim.  We assert that:
    - the key 'qa' exists in _V2_DISPATCH
    - calling the registered handler with a patched run_qa reaches it
      (mirrors test_mode_routing_contract.py's cross-wiring pattern).
    """
    from src.services.chat import router as r

    assert "qa" in r._V2_DISPATCH, (
        "'qa' is missing from router._V2_DISPATCH — mode would be unrouted."
    )


@pytest.mark.asyncio
async def test_v2_dispatch_qa_calls_run_qa(monkeypatch):
    """Calling _V2_DISPATCH['qa'] must invoke agents.qa.run_qa exactly once."""
    from src.services.chat import router as r
    from src.services.chat.agents import qa as qa_mod
    from src.services.chat.schemas._core import ChatRequest

    called: list[str] = []

    async def _fake_run_qa(req):
        called.append("run_qa")
        yield {"type": "meta", "mode": "qa"}
        yield {"type": "done"}

    monkeypatch.setattr(qa_mod, "run_qa", _fake_run_qa)

    req = ChatRequest(message="test", mode="qa")
    runner = r._V2_DISPATCH["qa"]
    events = [ev async for ev in runner(req, None)]

    assert called == ["run_qa"], (
        f"_V2_DISPATCH['qa'] did not call run_qa; got calls={called!r}"
    )
    assert events[0].get("mode") == "qa"
    assert events[-1]["type"] == "done"
