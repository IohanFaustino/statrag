"""`@tool retrieve_figures` — vector search over the image collections.

Wraps :func:`src.services.chat.retrieval.search_figures` so an LLM can ask for
figures relevant to a query without the orchestrator having to hardcode a
vision-mode branch.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

from src.services.chat.retrieval import search_figures


@tool
def retrieve_figures(
    query: str,
    k: int = 3,
    book_filter: Optional[list[str]] = None,
) -> str:
    """Search the textbook image collections for figures matching the query.

    Use this when a question is visual in nature or when an equation/plot is
    likely the best answer. Returns figure references with captions; pair with
    :func:`inspect_figure` to ask a vision model about a specific figure.

    Args:
        query: Natural-language search query describing the figure content.
        k: Maximum figures to return (1-8).
        book_filter: Optional list of book slugs to scope the search.

    Returns:
        A JSON string list of figure dicts, each with
        ``{ref, book, chapter, caption, chart}``.
    """
    figs = search_figures(query, book_slugs=book_filter, k=max(1, min(int(k), 8)))
    payload = [
        {
            "ref": f.ref,
            "book": f.book,
            "chapter": f.chapter,
            "caption": f.caption,
            "chart": f.chart,
        }
        for f in figs
    ]
    return json.dumps(payload, ensure_ascii=False)
