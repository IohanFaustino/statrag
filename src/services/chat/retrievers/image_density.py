"""Image candidate retrieval w/ co-location boost.

Pulls dense-similarity image candidates from the per-field ``_images``
collections then upweights those located in the same
``(book_slug, chapter_id)`` as the supplied text sections. Co-located
figures are typically the ones the textbook author intended to
illustrate the surrounding concept.

Returns a small candidate pool (default 6) that downstream judges score.

Chinese-wall: imports only from ``src.core.*`` and sibling
``src.services.chat.*``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.services.chat.retrieval import search_figures_with_scores
from src.services.chat.schemas import Figure, Source

logger = logging.getLogger(__name__)


@dataclass
class FigureCandidate:
    """One image candidate enriched w/ co-location score + provenance."""

    figure: Figure
    similarity: float          # raw dense score from Qdrant
    co_located: bool           # True if (book, chapter) matches a top text source
    combined: float            # similarity + co_location boost


def fetch_image_candidates(
    query: str,
    text_sources: list[Source],
    *,
    book_slugs: list[str] | None = None,
    pool: int = 6,
    co_location_boost: float = 0.15,
) -> list[FigureCandidate]:
    """Return up to *pool* image candidates ordered by combined score.

    Args:
        query: User query.
        text_sources: Top text sources chosen by the density retriever.
            Used to build the co-location set.
        book_slugs: Optional book scope (None = all books).
        pool: Maximum candidates to return.
        co_location_boost: Score added when (book, chapter) co-locates
            with at least one text source.
    """
    if not query.strip():
        return []
    pairs = search_figures_with_scores(query, book_slugs=book_slugs, k=max(pool * 2, 8))
    if not pairs:
        return []

    coloc_keys = {(s.book, s.chapter) for s in text_sources if s.book and s.chapter}

    out: list[FigureCandidate] = []
    for fig, score in pairs:
        co_loc = (fig.book, fig.chapter) in coloc_keys
        combined = float(score) + (co_location_boost if co_loc else 0.0)
        out.append(FigureCandidate(figure=fig, similarity=float(score),
                                   co_located=co_loc, combined=combined))
    out.sort(key=lambda c: c.combined, reverse=True)
    return out[:pool]
