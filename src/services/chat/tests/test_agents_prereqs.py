"""Tests for the Mode 6 prereqs pipeline: cycle detection, topo sort, graph wiring.

All tests mock LLM and Qdrant calls — no real network or DB connections.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat.agents.nodes import _detect_cycles, cycle_detect, sequence_topo
from src.services.chat.agents.state import AgentState


# ---------------------------------------------------------------------------
# _detect_cycles (pure function)
# ---------------------------------------------------------------------------


def _make_nodes(*ids: str) -> list[dict]:
    return [{"id": i} for i in ids]


def test_detect_cycles_no_cycle() -> None:
    """A DAG without cycles returns all valid edges and an empty removed list."""
    nodes = _make_nodes("a", "b", "c")
    edges = [
        {"from": "a", "to": "b", "weight": 1.0},
        {"from": "b", "to": "c", "weight": 1.0},
    ]
    clean, removed = _detect_cycles(nodes, edges)
    assert removed == []
    assert len(clean) == 2


def test_detect_cycles_simple_cycle() -> None:
    """A→B→A cycle: one back-edge removed, removed list is non-empty."""
    nodes = _make_nodes("a", "b")
    edges = [
        {"from": "a", "to": "b", "weight": 1.0},
        {"from": "b", "to": "a", "weight": 1.0},
    ]
    clean, removed = _detect_cycles(nodes, edges)
    assert len(removed) >= 1
    # Result must be acyclic: at most 1 edge remains
    assert len(clean) == 1


def test_detect_cycles_three_node_cycle() -> None:
    """A→B→C→A cycle: all three edges present; at least one removed."""
    nodes = _make_nodes("a", "b", "c")
    edges = [
        {"from": "a", "to": "b", "weight": 0.9},
        {"from": "b", "to": "c", "weight": 0.8},
        {"from": "c", "to": "a", "weight": 0.7},
    ]
    clean, removed = _detect_cycles(nodes, edges)
    assert len(removed) >= 1
    # The clean set must form a DAG (no cycle remains)
    # Verify by checking that topological sort yields all 3 nodes
    adj: dict[str, list[str]] = {"a": [], "b": [], "c": []}
    for e in clean:
        adj[e["from"]].append(e["to"])
    indeg = {"a": 0, "b": 0, "c": 0}
    for e in clean:
        indeg[e["to"]] += 1
    queue = [n for n, d in indeg.items() if d == 0]
    order: list[str] = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    assert len(order) == 3


def test_detect_cycles_unknown_node_edges_dropped() -> None:
    """Edges referencing unknown node ids are silently dropped."""
    nodes = _make_nodes("a", "b")
    edges = [
        {"from": "a", "to": "b"},
        {"from": "z", "to": "a"},   # z not in nodes
        {"from": "a", "to": "x"},  # x not in nodes
    ]
    clean, _ = _detect_cycles(nodes, edges)
    ids_used = {e.get("from") for e in clean} | {e.get("to") for e in clean}
    assert "z" not in ids_used
    assert "x" not in ids_used


def test_detect_cycles_cycles_broken_non_empty() -> None:
    """cycles_broken list is non-empty when at least one cycle is present."""
    nodes = _make_nodes("a", "b", "c")
    edges = [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": "a"},  # back-edge
    ]
    _, removed = _detect_cycles(nodes, edges)
    assert len(removed) >= 1


# ---------------------------------------------------------------------------
# cycle_detect node (async wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cycle_detect_node_populates_extras() -> None:
    """cycle_detect node stores removed descriptions in extras['cycles_broken']."""
    state = AgentState(
        concepts=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        edges=[
            {"from": "a", "to": "b", "weight": 1.0},
            {"from": "b", "to": "c", "weight": 1.0},
            {"from": "c", "to": "a", "weight": 1.0},  # cycle
        ],
    )
    result = await cycle_detect(state)
    assert "cycles_broken" in result.extras
    assert len(result.extras["cycles_broken"]) >= 1


@pytest.mark.asyncio
async def test_cycle_detect_node_no_cycle() -> None:
    """cycle_detect on a DAG sets cycles_broken to an empty list."""
    state = AgentState(
        concepts=[{"id": "x"}, {"id": "y"}],
        edges=[{"from": "x", "to": "y", "weight": 1.0}],
    )
    result = await cycle_detect(state)
    assert result.extras["cycles_broken"] == []


# ---------------------------------------------------------------------------
# sequence_topo node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topo_sort_linear_chain() -> None:
    """A linear A→B→C chain produces ordering ['a', 'b', 'c']."""
    state = AgentState(
        concepts=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        edges=[
            {"from": "a", "to": "b", "weight": 1.0},
            {"from": "b", "to": "c", "weight": 1.0},
        ],
    )
    result = await sequence_topo(state)
    order = result.extras["ordering"]
    assert order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_topo_sort_no_edges() -> None:
    """With no edges every node appears in the ordering (any order)."""
    state = AgentState(
        concepts=[{"id": "x"}, {"id": "y"}, {"id": "z"}],
        edges=[],
    )
    result = await sequence_topo(state)
    assert set(result.extras["ordering"]) == {"x", "y", "z"}


@pytest.mark.asyncio
async def test_topo_sort_diamond() -> None:
    """Diamond A→B, A→C, B→D, C→D: A comes first, D comes last."""
    state = AgentState(
        concepts=[{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
        edges=[
            {"from": "a", "to": "b"},
            {"from": "a", "to": "c"},
            {"from": "b", "to": "d"},
            {"from": "c", "to": "d"},
        ],
    )
    result = await sequence_topo(state)
    order = result.extras["ordering"]
    assert order[0] == "a"
    assert order[-1] == "d"
    assert len(order) == 4


@pytest.mark.asyncio
async def test_topo_sort_all_nodes_present() -> None:
    """Isolated nodes are appended so all concept ids appear in ordering."""
    state = AgentState(
        concepts=[{"id": "a"}, {"id": "b"}, {"id": "isolated"}],
        edges=[{"from": "a", "to": "b"}],
    )
    result = await sequence_topo(state)
    assert set(result.extras["ordering"]) == {"a", "b", "isolated"}


# ---------------------------------------------------------------------------
# run_prereqs integration (fully mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_prereqs_returns_dag() -> None:
    """run_prereqs assembles a DAG from mocked node outputs."""
    canned_concepts = [
        {"id": "linear_regression", "label": "Linear Regression",
         "source": {"book": "islp", "chapter": "ch03", "section": "3.1"}},
        {"id": "least_squares", "label": "Least Squares",
         "source": {"book": "islp", "chapter": "ch03", "section": "3.1.1"}},
    ]
    canned_edges = [
        {"from": "least_squares", "to": "linear_regression", "weight": 0.9}
    ]

    async def _mock_retrieve(s: AgentState) -> AgentState:
        s.sources = [MagicMock(book="islp", chapter="ch03", section="3.1",
                               chunk="text", score=0.9)]
        return s

    async def _mock_extract(s: AgentState) -> AgentState:
        s.concepts = canned_concepts
        s.qc_status = "pass"
        return s

    async def _mock_build_dag(s: AgentState) -> AgentState:
        s.edges = canned_edges
        return s

    with patch(
        "src.services.chat.agents.prereqs.retrieve_node", new=_mock_retrieve
    ), patch(
        "src.services.chat.agents.prereqs.extract_concepts", new=_mock_extract
    ), patch(
        "src.services.chat.agents.prereqs.build_dag", new=_mock_build_dag
    ), patch(
        "src.services.chat.agents.prereqs.upsert_concepts"
    ):
        from src.services.chat.agents.prereqs import run_prereqs

        dag = await run_prereqs("linear regression", book_slugs=["islp"])

    assert len(dag.nodes) == 2
    assert len(dag.edges) == 1
    assert dag.edges[0].from_id == "least_squares"
    assert dag.edges[0].to_id == "linear_regression"
    # cycle_detect + sequence_topo run on canned data; ordering must be set
    assert isinstance(dag.order, list)
    assert len(dag.order) == 2


@pytest.mark.asyncio
async def test_run_prereqs_with_cycle_broken() -> None:
    """run_prereqs breaks an injected A→B→C→A cycle; dag.cycles_broken is non-empty."""
    from src.services.chat.agents.graph import Node, StateGraph
    from src.services.chat.agents.nodes import cycle_detect, sequence_topo
    from src.services.chat.agents.prereqs import run_prereqs

    canned_concepts = [
        {"id": "a", "label": "A",
         "source": {"book": "b", "chapter": "c1", "section": "s1"}},
        {"id": "b_node", "label": "B",
         "source": {"book": "b", "chapter": "c1", "section": "s2"}},
        {"id": "c_node", "label": "C",
         "source": {"book": "b", "chapter": "c1", "section": "s3"}},
    ]
    # A→B→C→A cycle
    canned_edges = [
        {"from": "a", "to": "b_node", "weight": 1.0},
        {"from": "b_node", "to": "c_node", "weight": 1.0},
        {"from": "c_node", "to": "a", "weight": 1.0},
    ]

    async def _mock_retrieve(s: AgentState) -> AgentState:
        s.sources = [MagicMock(book="b", chapter="c1", section="s1",
                               chunk="text", score=0.8)]
        return s

    async def _mock_extract(s: AgentState) -> AgentState:
        s.concepts = canned_concepts
        s.qc_status = "pass"
        return s

    async def _mock_build_dag(s: AgentState) -> AgentState:
        s.edges = canned_edges
        return s

    with patch(
        "src.services.chat.agents.prereqs.retrieve_node", new=_mock_retrieve
    ), patch(
        "src.services.chat.agents.prereqs.extract_concepts", new=_mock_extract
    ), patch(
        "src.services.chat.agents.prereqs.build_dag", new=_mock_build_dag
    ), patch(
        "src.services.chat.agents.prereqs.upsert_concepts"
    ):
        dag = await run_prereqs("A concept", book_slugs=None)

    assert len(dag.cycles_broken) >= 1


@pytest.mark.asyncio
async def test_run_prereqs_upsert_failure_is_nonfatal() -> None:
    """A failure in upsert_concepts does not propagate as an exception."""

    async def _mock_retrieve(s: AgentState) -> AgentState:
        s.sources = [MagicMock(book="b", chapter="c1", section="s1",
                               chunk="t", score=0.5)]
        return s

    async def _mock_extract(s: AgentState) -> AgentState:
        s.concepts = [{"id": "x", "label": "X",
                       "source": {"book": "b", "chapter": "c1", "section": "s1"}}]
        s.qc_status = "pass"
        return s

    async def _mock_build_dag(s: AgentState) -> AgentState:
        s.edges = []
        return s

    def _boom(*_a: object, **_kw: object) -> None:
        raise RuntimeError("Qdrant down")

    with patch(
        "src.services.chat.agents.prereqs.retrieve_node", new=_mock_retrieve
    ), patch(
        "src.services.chat.agents.prereqs.extract_concepts", new=_mock_extract
    ), patch(
        "src.services.chat.agents.prereqs.build_dag", new=_mock_build_dag
    ), patch(
        "src.services.chat.agents.prereqs.upsert_concepts", side_effect=_boom
    ):
        from src.services.chat.agents.prereqs import run_prereqs
        # Should not raise
        dag = await run_prereqs("test", book_slugs=None)

    assert dag is not None
    assert len(dag.nodes) == 1
