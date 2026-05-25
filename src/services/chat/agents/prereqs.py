"""Mode 6 prereqs graph: retrieve → extract_concepts → build_dag → cycle_detect → sequence → emit DAG.

Chinese-wall: imports only from ``src.core.*`` and sibling chat modules.
ADR-001: roll-own runner; no LangGraph.
"""
from __future__ import annotations

import logging

from src.services.chat.agents.graph import Node, StateGraph
from src.services.chat.agents.nodes import (
    build_dag,
    cycle_detect,
    extract_concepts,
    retrieve_node,
    sequence_topo,
)
from src.services.chat.agents.state import AgentState
from src.services.chat.kg import fetch_concepts_by_label, upsert_concepts
from src.services.chat.schemas.output import DAG, Citation, ConceptEdge, ConceptNode

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Construct the prereqs :class:`~src.services.chat.agents.graph.StateGraph`.

    Node pipeline:
    1. ``retrieve`` — hybrid search to gather textbook sources.
    2. ``extract_concepts`` — LLM extracts up to 10 concepts.
    3. ``build_dag`` — LLM produces prerequisite edges.
    4. ``cycle_detect`` — DFS removes back-edges.
    5. ``sequence`` — topological sort into ``extras["ordering"]``.

    Returns:
        A :class:`~src.services.chat.agents.graph.StateGraph` ready to run.
    """
    return StateGraph(
        nodes=[
            Node("retrieve", retrieve_node),
            Node("extract_concepts", extract_concepts),
            Node("build_dag", build_dag),
            Node("cycle_detect", cycle_detect),
            Node("sequence", sequence_topo),
        ],
        max_iters=12,
    )


async def run_prereqs(query: str, book_slugs: list[str] | None) -> DAG:
    """Run the full prereqs graph and return a :class:`~src.services.chat.schemas.output.DAG`.

    Executes the 5-node pipeline, converts raw state dicts to Pydantic schema
    objects, and best-effort persists the result to the ``concepts_kg``
    Qdrant collection.

    Args:
        query: User query (the concept the student wants to understand).
        book_slugs: Optional list of book slugs to scope retrieval.

    Returns:
        A :class:`~src.services.chat.schemas.output.DAG` with ``nodes``,
        ``edges``, ``order``, and ``cycles_broken``.
    """
    state = AgentState(query=query, book_slugs=book_slugs)
    state = await build_graph().run(state)

    if state.errors:
        logger.warning("[prereqs] completed with errors: %s", state.errors)

    # Convert raw concept dicts to schema objects
    nodes: list[ConceptNode] = []
    for c in state.concepts:
        raw_src = c.get("source")
        citation: Citation | None = None
        if isinstance(raw_src, dict):
            try:
                citation = Citation(**raw_src)
            except Exception:  # noqa: BLE001
                pass
        nodes.append(
            ConceptNode(
                id=c["id"],
                label=c.get("label", c["id"]),
                source=citation,
            )
        )

    edges: list[ConceptEdge] = [
        ConceptEdge(
            from_id=e["from"],
            to_id=e["to"],
            weight=float(e.get("weight", 1.0)),
        )
        for e in state.edges
        if "from" in e and "to" in e
    ]

    # Best-effort persist to KG (non-fatal)
    try:
        upsert_concepts(nodes, edges)
    except Exception:  # noqa: BLE001
        logger.debug("[prereqs] upsert_concepts failed (non-fatal)")

    return DAG(
        target=query,
        nodes=nodes,
        edges=edges,
        order=state.extras.get("ordering", []),
        cycles_broken=state.extras.get("cycles_broken", []),
    )
