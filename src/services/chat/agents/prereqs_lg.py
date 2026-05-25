"""LangGraph re-implementation of the ``prereqs`` multi-agent graph (T11).

Same 5-node topology as v1 (``retrieve`` → ``extract_concepts`` → ``build_dag``
→ ``cycle_detect`` → ``sequence_topo``) but compiled by
``langgraph.graph.StateGraph`` so we get real graph semantics: conditional
edges, retry policies, native streaming, and a single source of truth for
multi-agent orchestration (ADR-006 supersedes ADR-001 for these modes).

Reuses the existing async node functions in :mod:`agents.nodes` by wrapping
them so they speak the dict-based LangGraph state contract.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from typing_extensions import TypedDict

from src.services.chat.agents.nodes import (
    build_dag,
    cycle_detect,
    extract_concepts,
    retrieve_node,
    sequence_topo,
)
from src.services.chat.agents.state import AgentState
from src.services.chat.kg import upsert_concepts
from src.services.chat.schemas.output import (
    Citation,
    ConceptEdge,
    ConceptNode,
    DAG,
)

logger = logging.getLogger(__name__)


class _PrereqsState(TypedDict, total=False):
    query: str
    book_slugs: list[str] | None
    sources: list[Any]
    concepts: list[dict]
    edges: list[dict]
    iter: int
    qc_status: str
    errors: list[str]
    extras: dict[str, Any]


def _to_agent_state(state: _PrereqsState) -> AgentState:
    return AgentState(
        query=state.get("query", ""),
        book_slugs=state.get("book_slugs"),
        sources=list(state.get("sources", [])),
        concepts=list(state.get("concepts", [])),
        edges=list(state.get("edges", [])),
        iter=state.get("iter", 0),
        qc_status=state.get("qc_status", "pending"),
        errors=list(state.get("errors", [])),
        extras=dict(state.get("extras", {})),
    )


def _from_agent_state(s: AgentState) -> dict:
    return {
        "sources": s.sources,
        "concepts": s.concepts,
        "edges": s.edges,
        "iter": s.iter,
        "qc_status": s.qc_status,
        "errors": s.errors,
        "extras": s.extras,
    }


def _wrap(node_fn):
    """Adapt ``AgentState -> AgentState`` async node to LangGraph dict state."""
    async def _runner(state: _PrereqsState) -> dict:
        result = await node_fn(_to_agent_state(state))
        return _from_agent_state(result)
    return _runner


def _build_graph():
    g = StateGraph(_PrereqsState)
    g.add_node("retrieve", _wrap(retrieve_node), retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("extract_concepts", _wrap(extract_concepts))
    g.add_node("build_dag", _wrap(build_dag))
    g.add_node("cycle_detect", _wrap(cycle_detect))
    g.add_node("sequence_topo", _wrap(sequence_topo))
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "extract_concepts")
    g.add_edge("extract_concepts", "build_dag")
    g.add_edge("build_dag", "cycle_detect")
    g.add_edge("cycle_detect", "sequence_topo")
    g.add_edge("sequence_topo", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


async def run_prereqs_lg(query: str, book_slugs: list[str] | None) -> DAG:
    """LangGraph-based replacement for :func:`agents.prereqs.run_prereqs`."""
    initial: _PrereqsState = {
        "query": query,
        "book_slugs": book_slugs,
        "sources": [],
        "concepts": [],
        "edges": [],
        "iter": 0,
        "qc_status": "pending",
        "errors": [],
        "extras": {},
    }
    final = await _graph().ainvoke(initial)

    nodes: list[ConceptNode] = []
    for c in final.get("concepts", []):
        raw_src = c.get("source")
        citation: Citation | None = None
        if isinstance(raw_src, dict):
            try:
                citation = Citation(**raw_src)
            except Exception:  # noqa: BLE001
                pass
        nodes.append(ConceptNode(
            id=c["id"],
            label=c.get("label", c["id"]),
            source=citation,
        ))

    edges: list[ConceptEdge] = [
        ConceptEdge(
            from_id=e["from"],
            to_id=e["to"],
            weight=float(e.get("weight", 1.0)),
        )
        for e in final.get("edges", [])
        if "from" in e and "to" in e
    ]

    try:
        upsert_concepts(nodes, edges)
    except Exception:  # noqa: BLE001
        logger.debug("[prereqs_lg] upsert_concepts failed (non-fatal)")

    return DAG(
        target=query,
        nodes=nodes,
        edges=edges,
        order=final.get("extras", {}).get("ordering", []),
        cycles_broken=final.get("extras", {}).get("cycles_broken", []),
    )
