"""Tests for the roll-own StateGraph runner (ADR-001).

All tests are unit-level: no Qdrant, no LLM, no network calls.
"""
from __future__ import annotations

import pytest

from src.services.chat.agents.graph import Node, StateGraph
from src.services.chat.agents.state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop(state: AgentState) -> AgentState:
    """Node that does nothing."""
    return state


async def _pass_node(state: AgentState) -> AgentState:
    """Node that records its own invocation and sets qc_status to pass."""
    state.extras.setdefault("calls", []).append("pass_node")
    state.qc_status = "pass"
    return state


async def _fail_node(state: AgentState) -> AgentState:
    """Node that always sets qc_status to fail."""
    state.extras.setdefault("calls", []).append("fail_node")
    state.qc_status = "fail"
    return state


async def _raise_node(state: AgentState) -> AgentState:
    """Node that raises an exception."""
    raise RuntimeError("intentional test error")


# ---------------------------------------------------------------------------
# iter cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iter_cap_breaks_loop() -> None:
    """When iter cap is hit before a node runs, an error is appended and loop stops."""
    call_log: list[str] = []

    async def counted_node(s: AgentState) -> AgentState:
        call_log.append("ran")
        return s

    # Three nodes but cap of 1 — only the first should run; second is blocked.
    graph = StateGraph(
        nodes=[
            Node("a", counted_node),
            Node("b", counted_node),
            Node("c", counted_node),
        ],
        max_iters=1,
    )
    state = await graph.run(AgentState())

    # After node "a" runs iter becomes 1; node "b" is blocked by cap.
    assert len(call_log) == 1
    assert any("iter cap hit" in e for e in state.errors)


@pytest.mark.asyncio
async def test_iter_cap_error_contains_node_name() -> None:
    """The iter-cap error message includes the name of the blocked node."""
    graph = StateGraph(
        nodes=[Node("first", _noop), Node("blocked_node", _noop)],
        max_iters=1,
    )
    state = await graph.run(AgentState())
    assert any("blocked_node" in e for e in state.errors)


# ---------------------------------------------------------------------------
# retry on fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_previous_node_called_on_fail() -> None:
    """When node[1] sets qc_status='fail', node[0] is retried once."""
    call_log: list[str] = []

    async def node_a(s: AgentState) -> AgentState:
        call_log.append("a")
        return s

    async def node_b(s: AgentState) -> AgentState:
        call_log.append("b")
        s.qc_status = "fail"
        return s

    graph = StateGraph(
        nodes=[Node("a", node_a), Node("b", node_b)],
        max_iters=12,
    )
    await graph.run(AgentState())

    # node_a should have been called twice: original run + retry after node_b fails
    assert call_log.count("a") == 2
    assert call_log.count("b") == 1


@pytest.mark.asyncio
async def test_no_retry_for_first_node_fail() -> None:
    """When the very first node fails, no retry occurs (idx == 0)."""
    call_log: list[str] = []

    async def node_a(s: AgentState) -> AgentState:
        call_log.append("a")
        s.qc_status = "fail"
        return s

    graph = StateGraph(nodes=[Node("a", node_a)], max_iters=12)
    state = await graph.run(AgentState())

    # node_a only called once; no previous node to retry
    assert call_log.count("a") == 1
    assert state.qc_status == "fail"


@pytest.mark.asyncio
async def test_retry_resets_qc_status_to_pending() -> None:
    """qc_status is reset to 'pending' before the retry node runs."""
    observed_status: list[str] = []

    async def recording_node(s: AgentState) -> AgentState:
        observed_status.append(s.qc_status)
        return s

    async def always_fail(s: AgentState) -> AgentState:
        s.qc_status = "fail"
        return s

    graph = StateGraph(
        nodes=[Node("recorder", recording_node), Node("failer", always_fail)],
        max_iters=12,
    )
    await graph.run(AgentState())

    # The retry call of recording_node sees "pending", not "fail"
    assert "pending" in observed_status


# ---------------------------------------------------------------------------
# exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_exception_recorded_in_errors() -> None:
    """An exception raised by a node is caught and appended to state.errors."""
    graph = StateGraph(nodes=[Node("raiser", _raise_node)], max_iters=12)
    state = await graph.run(AgentState())

    assert any("RuntimeError" in e for e in state.errors)
    assert any("intentional test error" in e for e in state.errors)


@pytest.mark.asyncio
async def test_node_exception_sets_qc_fail() -> None:
    """An unhandled node exception sets qc_status to 'fail'."""
    graph = StateGraph(nodes=[Node("raiser", _raise_node)], max_iters=12)
    state = await graph.run(AgentState())
    assert state.qc_status == "fail"


# ---------------------------------------------------------------------------
# empty nodes list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_nodes_returns_state_untouched() -> None:
    """An empty node list returns the initial state with no modifications."""
    initial = AgentState(query="hello", iter=0)
    graph = StateGraph(nodes=[], max_iters=12)
    result = await graph.run(initial)

    assert result.query == "hello"
    assert result.iter == 0
    assert result.errors == []


# ---------------------------------------------------------------------------
# state mutation propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_mutations_propagate_between_nodes() -> None:
    """Each node sees the state mutations made by previous nodes."""

    async def set_extra(s: AgentState) -> AgentState:
        s.extras["x"] = 42
        return s

    async def read_extra(s: AgentState) -> AgentState:
        s.extras["y"] = s.extras.get("x", 0) * 2
        return s

    graph = StateGraph(
        nodes=[Node("set", set_extra), Node("read", read_extra)], max_iters=12
    )
    state = await graph.run(AgentState())

    assert state.extras["y"] == 84


@pytest.mark.asyncio
async def test_iter_increments_per_node() -> None:
    """iter counter increments by 1 for every node that runs."""
    graph = StateGraph(
        nodes=[Node("a", _noop), Node("b", _noop), Node("c", _noop)], max_iters=12
    )
    state = await graph.run(AgentState())
    assert state.iter == 3
