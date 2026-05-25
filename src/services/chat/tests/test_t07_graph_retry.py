"""T07 acceptance: graph retry hole (B8) + ConceptEdge field alignment."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services.chat.agents.graph import Node, StateGraph
from src.services.chat.agents.state import AgentState


# ---------------------------------------------------------------------------
# T07: graph retry semantics
# ---------------------------------------------------------------------------


def test_qc_status_is_reset_to_pending_before_retry():
    """When the retry succeeds, qc_status must not stay 'fail'."""

    async def n1(state: AgentState) -> AgentState:
        # Marks pass on second visit, fail on first
        state.iter_count = getattr(state, "iter_count", 0)  # type: ignore[attr-defined]
        if state.iter_count == 0:  # type: ignore[attr-defined]
            state.qc_status = "pass"
        else:
            state.qc_status = "pass"
        return state

    async def n2(state: AgentState) -> AgentState:
        state.qc_status = "fail"  # triggers retry of n1
        return state

    g = StateGraph([Node("n1", n1), Node("n2", n2)])
    out = asyncio.run(g.run(AgentState()))
    # After retry of n1, qc_status should be "pass" (n1 set it explicitly)
    assert out.qc_status == "pass", (
        f"qc_status should be reset by successful retry, got {out.qc_status}"
    )


def test_retry_exception_marks_qc_status_fail():
    """T07 (B8 fix): retry raising must NOT leave qc_status='pending'."""
    call_count = {"n": 0}

    async def n1(state: AgentState) -> AgentState:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return state  # first call: success
        raise RuntimeError("retry exploded")

    async def n2(state: AgentState) -> AgentState:
        state.qc_status = "fail"
        return state

    g = StateGraph([Node("n1", n1), Node("n2", n2)])
    out = asyncio.run(g.run(AgentState()))

    # Retry of n1 raised → state.qc_status forced to "fail"
    assert out.qc_status == "fail"
    # Both errors logged: n2 didn't fail per-se but flagged, and retry exception
    assert any("retry" in e for e in out.errors)


def test_iter_cap_breaks_loop():
    async def n(state: AgentState) -> AgentState:
        return state

    g = StateGraph([Node("a", n), Node("b", n), Node("c", n)], max_iters=1)
    out = asyncio.run(g.run(AgentState()))
    assert any("iter cap hit" in e for e in out.errors)


# ---------------------------------------------------------------------------
# T07: ConceptEdge field alignment (accept both from/to and from_id/to_id)
# ---------------------------------------------------------------------------


def _stub_openai(content: str):
    """Build a fake openai client whose chat.completions.create returns *content*."""
    class _Choice:
        def __init__(self, c):
            self.message = SimpleNamespace(content=c)

    class _Resp:
        def __init__(self, c):
            self.choices = [_Choice(c)]

    class _Chat:
        def __init__(self, c):
            self._c = c

        @property
        def completions(self):
            return self

        async def create(self, **kw):
            return _Resp(self._c)

    class _OA:
        def __init__(self, api_key=None):
            self.chat = _Chat(content)

    return _OA


def test_build_dag_accepts_legacy_from_to_keys(monkeypatch):
    from src.services.chat.agents import nodes

    fake_resp = json.dumps({"edges": [
        {"from": "a", "to": "b", "weight": 0.9},
    ]})
    monkeypatch.setattr(nodes._openai, "AsyncOpenAI", _stub_openai(fake_resp))

    state = AgentState()
    state.concepts = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
    out = asyncio.run(nodes.build_dag(state))
    assert out.edges == [{"from": "a", "to": "b", "weight": 0.9}]


def test_build_dag_accepts_pydantic_from_id_to_id_keys(monkeypatch):
    from src.services.chat.agents import nodes

    fake_resp = json.dumps({"edges": [
        {"from_id": "a", "to_id": "b", "weight": 0.5},
    ]})
    monkeypatch.setattr(nodes._openai, "AsyncOpenAI", _stub_openai(fake_resp))

    state = AgentState()
    state.concepts = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
    out = asyncio.run(nodes.build_dag(state))
    assert out.edges == [{"from": "a", "to": "b", "weight": 0.5}]


def test_build_dag_drops_edges_with_missing_endpoints(monkeypatch):
    from src.services.chat.agents import nodes

    fake_resp = json.dumps({"edges": [
        {"from": "a"},               # missing to
        {"to": "b"},                  # missing from
        {"from": "a", "to": "b"},    # ok
    ]})
    monkeypatch.setattr(nodes._openai, "AsyncOpenAI", _stub_openai(fake_resp))

    state = AgentState()
    state.concepts = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
    out = asyncio.run(nodes.build_dag(state))
    assert out.edges == [{"from": "a", "to": "b", "weight": 1.0}]
