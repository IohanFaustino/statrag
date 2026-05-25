"""`@tool retrieve` — LangChain-compatible hybrid retriever.

Wraps the synchronous :func:`src.services.chat.retrieval.hybrid_search` so an
LLM agent built with :func:`langchain.agents.create_agent` can call it
mid-generation. Each invocation returns a JSON-serialisable summary of the top
hits — short enough that the agent's context window does not balloon.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

from src.services.chat.retrieval import hybrid_search


@tool
def retrieve(
    query: str,
    k: int = 5,
    book_filter: Optional[list[str]] = None,
    rerank: bool = True,
    adjacent_sections: bool = False,
) -> str:
    """Search the textbook corpus for passages relevant to a query.

    Use this tool when you need to ground an answer in textbook content. Each
    call returns the top *k* matching sections with book / chapter / section
    citations and a short text excerpt — call it again with a refined query if
    the first result set misses the user's intent.

    Args:
        query: Natural-language search query. Specific is better than vague.
        k: Maximum number of sections to return (1-10).
        book_filter: Optional list of book slugs to restrict the search. When
            omitted, all books in the corpus are searched.
        rerank: When True, apply cross-encoder reranking after RRF fusion.
        adjacent_sections: When True, expand each hit with its same-section
            neighbouring chunks for richer context (useful for math / figures).

    Returns:
        A JSON string list of source dicts. T13-C: each entry exposes the
        full provenance the LLM needs to write APA-style citations:
        ``{rank, book, book_name, authors_short, year, chapter, section,
        title, page_from, page_to, chunk, excerpt, score, chunkId}``.
        ``chunk`` is the body text truncated to ~1500 chars; ``excerpt`` is
        the legacy 200-char preview kept for downstream chip rendering.
    """
    sources, _meta = hybrid_search(
        query,
        book_slugs=book_filter,
        top_k=max(1, min(int(k), 10)),
        rerank=rerank,
        adjacent_sections=adjacent_sections,
    )
    payload = [
        {
            "rank": s.rank,
            "book": s.book,
            "book_name": s.book_name or s.book,
            "authors": s.authors,
            "authors_short": s.authors_short,
            "year": s.year,
            "chapter": s.chapter,
            "section": s.section,
            "title": s.title,
            "page_from": s.page_from,
            "page_to": s.page_to,
            "page": s.page,
            "excerpt": s.excerpt,
            "chunk": (s.chunk or "")[:1500],
            "score": round(float(s.score), 4),
            "chunkId": s.chunkId,
        }
        for s in sources
    ]
    return json.dumps(payload, ensure_ascii=False)
