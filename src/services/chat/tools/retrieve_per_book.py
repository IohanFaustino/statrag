"""`@tool retrieve_per_book` — per-book parallel retrieval for compare mode.

Runs :func:`hybrid_search` once per requested book (fan-out via
``asyncio.gather``) and returns the top hits grouped by book. Used by the
``compare`` mode so the LLM always sees balanced coverage instead of one book
dominating the candidate set (B9 fix).

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool

from src.services.chat.retrieval import hybrid_search


@tool
def retrieve_per_book(
    query: str,
    books: list[str],
    k_per_book: int = 3,
    rerank: bool = True,
) -> str:
    """Search the textbook corpus separately for each book listed.

    Use this tool when comparing how multiple textbooks treat the same
    concept. Each book gets its own retrieval pool so no single book
    dominates the result set.

    Args:
        query: Natural-language search query.
        books: List of book slugs to search; each receives its own retrieval
            pass.
        k_per_book: Maximum sections returned per book (1-8).
        rerank: When True, apply cross-encoder reranking per book.

    Returns:
        A JSON string mapping book slug to its list of source dicts.
        Each source has the same shape as :func:`retrieve`.
    """
    k_per_book = max(1, min(int(k_per_book), 8))

    async def _one(book: str):
        sources, _ = await asyncio.to_thread(
            hybrid_search,
            query,
            book_slugs=[book],
            top_k=k_per_book,
            rerank=rerank,
        )
        return book, sources

    async def _all():
        return await asyncio.gather(*[_one(b) for b in books])

    results = asyncio.run(_all())

    payload: dict[str, list[dict]] = {}
    for book, sources in results:
        payload[book] = [
            {
                "rank": s.rank,
                "book": s.book,
                "chapter": s.chapter,
                "section": s.section,
                "title": s.title,
                "excerpt": s.excerpt,
                "score": round(float(s.score), 4),
                "chunkId": s.chunkId,
            }
            for s in sources
        ]
    return json.dumps(payload, ensure_ascii=False)
