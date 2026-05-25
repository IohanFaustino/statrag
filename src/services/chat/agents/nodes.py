"""Generic reusable graph nodes for multi-agent modes.

Each node is an async function that receives and returns :class:`AgentState`.

Chinese-wall: imports only from ``src.core.*`` and sibling chat modules.
ADR-001: roll-own runner; no LangGraph.
"""
from __future__ import annotations

import asyncio
import json
import logging

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents.state import AgentState
from src.services.chat.retrieval import hybrid_search

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# retrieve_node
# ---------------------------------------------------------------------------


async def retrieve_node(state: AgentState) -> AgentState:
    """Hybrid retrieval against the configured book_slugs.

    Runs :func:`~src.services.chat.retrieval.hybrid_search` in a thread
    (it is synchronous / blocking) and stores the resulting sources on
    ``state.sources``.

    Args:
        state: Current graph state; reads ``query`` and ``book_slugs``.

    Returns:
        Updated state with ``sources`` populated.
    """
    src, _meta = await asyncio.to_thread(
        hybrid_search,
        state.query,
        book_slugs=state.book_slugs,
        top_k=8,
        rerank=True,
    )
    state.sources = src
    return state


# ---------------------------------------------------------------------------
# extract_concepts
# ---------------------------------------------------------------------------


async def extract_concepts(state: AgentState) -> AgentState:
    """LLM-extract a list of concepts referenced in the retrieved sources.

    Each concept dict has the shape::

        {"id": "snake_case_id", "label": "Short Label",
         "source": {"book": "...", "chapter": "...", "section": "..."}}

    Sets ``qc_status = "pass"`` on success, ``"fail"`` when no sources are
    available or the LLM returns invalid JSON.

    Args:
        state: Current graph state; reads ``sources``.

    Returns:
        Updated state with ``concepts`` populated and ``qc_status`` set.
    """
    if not state.sources:
        state.qc_status = "fail"
        state.errors.append("extract_concepts: no sources")
        return state

    excerpts = "\n\n".join(
        f"[{i + 1}] {s.book} {s.chapter} {s.section}\n{(s.chunk or '')[:1500]}"
        for i, s in enumerate(state.sources[:5])
    )
    prompt = (
        "From the following textbook excerpts, extract up to 10 distinct technical "
        "concepts that a student would need to understand. For each, output an id "
        "(snake_case), a short label, and the source citation (book/chapter/section). "
        'Return ONLY JSON: {"concepts": [{"id": "...", "label": "...", '
        '"source": {"book": "...", "chapter": "...", "section": "..."}}]}.\n\n'
        f"{excerpts}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await oa.chat.completions.create(
        model=settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.1,
    )
    raw = strip_fences(resp.choices[0].message.content or "{}")
    try:
        j = json.loads(raw)
        state.concepts = j.get("concepts", [])
        state.qc_status = "pass" if state.concepts else "fail"
        if not state.concepts:
            state.errors.append("extract_concepts: empty concept list")
    except json.JSONDecodeError:
        state.qc_status = "fail"
        state.errors.append("extract_concepts: JSON parse error")
    return state


# ---------------------------------------------------------------------------
# build_dag
# ---------------------------------------------------------------------------


async def build_dag(state: AgentState) -> AgentState:
    """LLM-extract prerequisite edges among the listed concepts.

    Produces directed edges of the form ``{"from": id_a, "to": id_b,
    "weight": 0.0-1.0}`` where ``from`` must be understood *before* ``to``.

    Args:
        state: Current graph state; reads ``concepts``.

    Returns:
        Updated state with ``edges`` populated.
    """
    if not state.concepts:
        state.qc_status = "fail"
        state.errors.append("build_dag: no concepts to build edges from")
        return state

    concept_list = "\n".join(f"- {c['id']}: {c['label']}" for c in state.concepts)
    prompt = (
        "Given these concepts, identify which concepts are prerequisites of "
        "which others. Use ONLY the listed concept ids. Avoid cycles. Output "
        'edges as JSON: {"edges": [{"from": "id_a", "to": "id_b", '
        '"weight": 0.0-1.0}]}\n\n'
        f"Concepts:\n{concept_list}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await oa.chat.completions.create(
        model=settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.0,
    )
    raw = strip_fences(resp.choices[0].message.content or "{}")
    try:
        edges_raw = json.loads(raw).get("edges", [])
    except json.JSONDecodeError:
        state.edges = []
        state.errors.append("build_dag: JSON parse error — edges set to []")
    else:
        # T07: accept both legacy {"from","to"} and Pydantic-aligned
        # {"from_id","to_id"} field names from the LLM. Downstream cycle_detect
        # consumes "from"/"to" keys, so we always normalise to those.
        normalised: list[dict] = []
        for e in edges_raw:
            if not isinstance(e, dict):
                continue
            f = e.get("from", e.get("from_id"))
            t = e.get("to", e.get("to_id"))
            if not (f and t):
                continue
            normalised.append({
                "from": f,
                "to": t,
                "weight": float(e.get("weight", 1.0)),
            })
        state.edges = normalised
    return state


# ---------------------------------------------------------------------------
# cycle detection helpers
# ---------------------------------------------------------------------------


def _detect_cycles(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[str]]:
    """Return (cleaned_edges, removed_descriptions) after breaking cycles via DFS.

    Uses an iterative colour-marking DFS (white=0 / grey=1 / black=2) to
    detect back-edges and remove them.  Only edges whose endpoints exist in
    *nodes* are kept.

    Args:
        nodes: Concept node dicts, each must have an ``"id"`` key.
        edges: Edge dicts with ``"from"`` and ``"to"`` keys.

    Returns:
        A tuple of ``(clean_edges, removed_descriptions)`` where
        ``removed_descriptions`` is a list of ``"from_id->to_id"`` strings.
    """
    id_set: set[str] = {n["id"] for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in id_set and t in id_set:
            adj[f].append(t)

    removed: list[str] = []
    visited: dict[str, int] = {n: 0 for n in adj}  # 0=white 1=grey 2=black

    def visit(u: str) -> bool:
        """DFS visit; returns True if a back-edge was discovered."""
        if visited[u] == 1:
            return True
        if visited[u] == 2:
            return False
        visited[u] = 1
        for v in list(adj[u]):
            if visit(v):
                adj[u].remove(v)
                removed.append(f"{u}->{v}")
        visited[u] = 2
        return False

    for n in list(adj):
        if visited[n] == 0:
            visit(n)

    clean = [
        e
        for e in edges
        if e.get("from") in adj and e.get("to") in adj.get(e.get("from", ""), [])
    ]
    return clean, removed


# ---------------------------------------------------------------------------
# cycle_detect node
# ---------------------------------------------------------------------------


async def cycle_detect(state: AgentState) -> AgentState:
    """Remove cycles from ``state.edges`` in-place.

    Writes removed edge descriptions to ``state.extras["cycles_broken"]``.

    Args:
        state: Current graph state; reads and mutates ``concepts`` and ``edges``.

    Returns:
        Updated state with acyclic ``edges`` and ``extras["cycles_broken"]``.
    """
    clean, removed = _detect_cycles(state.concepts, state.edges)
    state.edges = clean
    state.extras["cycles_broken"] = removed
    return state


# ---------------------------------------------------------------------------
# sequence_topo node
# ---------------------------------------------------------------------------


async def sequence_topo(state: AgentState) -> AgentState:
    """Topological sort of concepts; result stored in ``state.extras["ordering"]``.

    Uses Kahn's algorithm (queue-based BFS).  Any concept not reachable via
    the sorted order (disconnected or filtered by cycle removal) is appended
    at the end.

    Args:
        state: Current graph state; reads ``concepts`` and ``edges``.

    Returns:
        Updated state with ``extras["ordering"]`` set to a list of concept ids.
    """
    adj: dict[str, list[str]] = {n["id"]: [] for n in state.concepts}
    indeg: dict[str, int] = {n["id"]: 0 for n in state.concepts}

    for e in state.edges:
        f, t = e.get("from"), e.get("to")
        if f in adj and t in adj:
            adj[f].append(t)
            indeg[t] += 1

    queue: list[str] = [n for n, d in indeg.items() if d == 0]
    order: list[str] = []
    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)

    # Append any nodes not reached (isolated or cycle remnants)
    seen = set(order)
    for n in adj:
        if n not in seen:
            order.append(n)

    state.extras["ordering"] = order
    return state
