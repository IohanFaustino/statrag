"""`@tool kg_neighbors` — look up concept-graph neighbours from the KG.

Reads :func:`src.services.chat.kg.fetch_concepts_by_label` (or by id) and
returns the surrounding concept neighbourhood, useful for prereqs / annotate
context expansion.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from src.services.chat import kg

logger = logging.getLogger(__name__)


@tool
def kg_neighbors(label: str, k: int = 5) -> str:
    """Look up related concepts in the knowledge graph.

    Use this to find prerequisites or related ideas for a concept the user
    is asking about. Returns concept ids + labels + citations.

    Args:
        label: Concept label or id to search for (case-insensitive substring
            match against canonical labels).
        k: Maximum neighbours to return (1-15).

    Returns:
        A JSON string list of concept dicts:
        ``{id, label, source: {book, chapter, section}}``.
    """
    k = max(1, min(int(k), 15))
    try:
        results = kg.fetch_concepts_by_label(label, k=k)
    except Exception:  # noqa: BLE001
        logger.exception("kg_neighbors: lookup failed for %s", label)
        results = []

    payload: list[dict] = []
    for r in results:
        item = {"id": r.get("id"), "label": r.get("label")}
        src = r.get("source")
        if isinstance(src, dict):
            item["source"] = {
                "book": src.get("book", ""),
                "chapter": src.get("chapter", ""),
                "section": src.get("section", ""),
            }
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False)
