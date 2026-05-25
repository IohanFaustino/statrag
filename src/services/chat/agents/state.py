"""Shared mutable state passed through a state graph.

Chinese-wall: imports only stdlib.
ADR-001: roll-own runner; no LangGraph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Shared state passed through a state graph.

    Generic enough for prereqs / research / study_path.  Each node may
    mutate or extend it.  Fields are optional and populated lazily.

    Attributes:
        query: The original user query string.
        book_slugs: Optional list of book slugs to scope retrieval.
        sources: Accumulated retrieval results (list of Source objects).
        concepts: Extracted concept dicts, each with id/label/source keys.
        edges: Directed edges between concept ids, each with from/to/weight.
        claims: Research claims (mode 8).
        output: Final structured output (set by last node or emit step).
        iter: Running iteration counter incremented by the graph runner.
        qc_status: Quality-control gate — ``"pending"`` | ``"pass"`` | ``"fail"``.
        errors: Accumulated error messages from failed nodes.
        extras: Per-graph scratch dict for node-specific side-channel data.
    """

    query: str = ""
    book_slugs: list[str] | None = None
    sources: list[Any] = field(default_factory=list)         # list[Source]
    concepts: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    output: Any = None                                        # final structured output
    iter: int = 0
    qc_status: str = "pending"                                # pending|pass|fail
    errors: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)      # per-graph scratch
