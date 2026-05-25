"""Concept-density retriever for deep tutor mode.

Two-stage retrieval:
    Stage 1 (coarse) — hybrid RRF search returns a wide candidate pool.
    For each candidate chunk count occurrences of supplied *concepts*.
    Aggregate to (book_slug, section_id); rank sections by
    ``alpha * normalized_concept_count + beta * normalized_max_rrf_score``.

    Stage 2 (fine) — fetch every chunk belonging to the top-N sections via
    Qdrant scroll (true context expansion, not just one-hop neighbours).
    Run the cross-encoder reranker over the expanded pool against the
    original query to keep the survivors well-ordered.

Returned Sources retain their original Qdrant payload metadata, so the
downstream prompt can quote / cite them exactly as the standard hybrid
retriever does.

Chinese-wall: imports only from ``src.core.*`` and sibling
``src.services.chat.*`` modules.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchAny, Range

from src.core.config import settings
from src.core.qdrant_store import client
from src.services.chat.books import collections_for_books, list_books
from src.services.chat.rerankers import get_reranker
from src.services.chat.retrieval import _point_to_source, hybrid_search
from src.services.chat.schemas import RetrievalMetadata, Source

logger = logging.getLogger(__name__)

_WORD_BOUND = re.compile(r"\b")


def _count_occurrences(text: str, term: str) -> int:
    """Whole-word, case-insensitive count of *term* inside *text*.

    Falls back to substring match when the term contains no word
    characters (e.g. math symbol, hyphenated phrase).
    """
    if not text or not term:
        return 0
    haystack = text.lower()
    needle = term.lower().strip()
    if not needle:
        return 0
    if not any(c.isalnum() for c in needle):
        return haystack.count(needle)
    pattern = re.compile(rf"\b{re.escape(needle)}\b")
    return len(pattern.findall(haystack))


def _section_score(count_norm: float, rrf_norm: float, alpha: float = 0.6) -> float:
    return alpha * count_norm + (1.0 - alpha) * rrf_norm


def _fetch_section_chunks(
    book_slug: str,
    section_id: str,
    collections: list[str],
    seen_ids: set[str],
    max_per_section: int = 12,
) -> list[Any]:
    """Scroll every chunk for ``(book_slug, section_id)`` not in *seen_ids*."""
    flt = Filter(
        must=[
            FieldCondition(key="book_slug", match=MatchAny(any=[book_slug])),
            FieldCondition(key="section_id", match=MatchAny(any=[section_id])),
        ]
    )
    out: list[Any] = []
    for collection in collections:
        try:
            res = client().scroll(
                collection_name=collection,
                scroll_filter=flt,
                limit=max_per_section,
                with_payload=True,
            )
            for p in res[0]:
                pid = str(p.id)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                # ``scroll`` returns ``Record`` (pydantic, frozen) — no
                # ``score`` attribute. Wrap in a lightweight pseudo-point
                # so downstream ``_point_to_source`` can read ``.score``.
                out.append(_PseudoPoint(pid, 0.001, p.payload or {}))
        except Exception:  # noqa: BLE001
            logger.exception("scroll failed for %s/%s in %s", book_slug, section_id, collection)
    return out


def _parent_section(section_id: str) -> str:
    """Parent of a dotted section id: ``"2.2.1" → "2.2"``; top-level unchanged."""
    parts = (section_id or "").split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else (section_id or "")


def _fetch_neighbor_chunks(
    book_slug: str,
    section_id: str,
    page_from: int | None,
    collections: list[str],
    seen_ids: set[str],
    *,
    max_lead: int = 2,
    page_band: int = 25,
) -> list[Any]:
    """Lead chunks of the immediately preceding/following SIBLING sections
    (same parent), found via the ``page_from`` reading order within a page band.

    Best-effort: returns ``[]`` on any error or missing ``page_from``. These are
    low-score candidates; the caller's cross-encoder rerank is the gate that
    decides whether they survive the ``final_top_n`` cut.
    """
    if page_from is None:
        return []
    parent = _parent_section(section_id)
    flt = Filter(
        must=[
            FieldCondition(key="book_slug", match=MatchAny(any=[book_slug])),
            FieldCondition(key="page_from", range=Range(gte=page_from - page_band, lte=page_from + page_band)),
        ]
    )
    rows: list[tuple[int, str, dict, str]] = []
    for collection in collections:
        try:
            res = client().scroll(
                collection_name=collection, scroll_filter=flt, limit=120, with_payload=True,
            )
            for p in res[0]:
                pl = p.payload or {}
                sid = str(pl.get("section_id") or "")
                pf = pl.get("page_from")
                if not sid or sid == section_id or pf is None:
                    continue
                rows.append((int(pf), sid, pl, str(p.id)))
        except Exception:  # noqa: BLE001
            logger.exception("neighbor scroll failed for %s/%s in %s", book_slug, section_id, collection)
    if not rows:
        return []
    siblings = [r for r in rows if _parent_section(r[1]) == parent] or rows  # fallback: any neighbor
    before = sorted((r for r in siblings if r[0] < page_from), key=lambda r: -r[0])
    after = sorted((r for r in siblings if r[0] >= page_from), key=lambda r: r[0])
    out: list[Any] = []
    for group in (before, after):
        if not group:
            continue
        nbr_sid = group[0][1]  # nearest neighbor section
        lead = [r for r in group if r[1] == nbr_sid][:max_lead]
        for _pf, _sid, pl, pid in lead:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            out.append(_PseudoPoint(pid, 0.0005, pl))
    return out


def concept_density_search(
    query: str,
    concepts: list[str],
    *,
    book_slugs: list[str] | None = None,
    top_sections: int = 5,
    final_top_n: int = 8,
    candidate_pool: int | None = None,
) -> tuple[list[Source], RetrievalMetadata]:
    """Two-stage concept-density retrieval.

    Args:
        query: Original user question.
        concepts: 1-3 normalized concept strings extracted from the query.
        book_slugs: Optional book scope (None = all books).
        top_sections: How many high-density sections to expand.
        final_top_n: How many chunks to return after rerank.
        candidate_pool: Override for the Stage-1 candidate pool size.

    Returns:
        (sources, metadata) — sources ordered by reranker score, ranks 1-N.
    """
    t0 = time.monotonic()

    if not concepts:
        # Degenerate path: behave like a standard hybrid query with
        # adjacent-section expansion + rerank.
        sources, meta = hybrid_search(
            query,
            book_slugs=book_slugs,
            top_k=final_top_n,
            rerank=True,
            rerank_top_n=final_top_n,
            adjacent_sections=True,
        )
        meta = RetrievalMetadata(
            rewrittenQuery=meta.rewrittenQuery,
            embedding=meta.embedding,
            retrievalMs=meta.retrievalMs,
            collections=meta.collections,
            filter=meta.filter,
            topK=final_top_n,
            scoreThreshold=meta.scoreThreshold,
            mode="density (degenerate -> hybrid + adjacent + rerank)",
        )
        return sources, meta

    pool = candidate_pool or settings.rerank_top_k_in

    effective_slugs = book_slugs or [b.id for b in list_books()]
    coll_map = collections_for_books(effective_slugs)
    collections_hit = list(coll_map.keys())

    candidates, _ = hybrid_search(
        query,
        book_slugs=book_slugs,
        top_k=pool,
        rerank=False,
    )

    # Aggregate counts per (book_slug, section_id) ----------------------------
    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "max_score": 0.0, "first_src": None, "chunk_ids": []}
    )
    max_count = 1
    max_score = 1e-9
    for src in candidates:
        c_text = src.chunk or src.excerpt or ""
        total = sum(_count_occurrences(c_text, c) for c in concepts)
        key = (src.book, src.section)
        bucket = agg[key]
        bucket["count"] += total
        bucket["max_score"] = max(bucket["max_score"], float(src.score))
        bucket["chunk_ids"].append(src.chunkId)
        if bucket["first_src"] is None:
            bucket["first_src"] = src
        if bucket["count"] > max_count:
            max_count = bucket["count"]
        if bucket["max_score"] > max_score:
            max_score = bucket["max_score"]

    # Score sections, drop those with zero concept count ----------------------
    scored: list[tuple[tuple[str, str], float, dict[str, Any]]] = []
    for key, bucket in agg.items():
        count_norm = bucket["count"] / max_count
        rrf_norm = bucket["max_score"] / max_score
        score = _section_score(count_norm, rrf_norm)
        scored.append((key, score, bucket))
    scored.sort(key=lambda t: t[1], reverse=True)

    # Filter: keep only sections that had at least one concept hit OR fall
    # back to the top by rrf score when concept count is uniformly zero.
    with_hits = [t for t in scored if t[2]["count"] > 0]
    final_sections = (with_hits or scored)[:top_sections]

    # Stage 2 — fetch every chunk of each survivor section --------------------
    seen_ids: set[str] = set()
    expanded_points: list[Any] = []
    for (book_slug, section_id), _score, bucket in final_sections:
        # Seed with the candidates we already have for this section ----------
        for src in candidates:
            if src.book == book_slug and src.section == section_id and src.chunkId not in seen_ids:
                seen_ids.add(src.chunkId)
                expanded_points.append(_source_to_pseudo_point(src))
        # Pull any remaining chunks of the section ---------------------------
        extra = _fetch_section_chunks(book_slug, section_id, collections_hit, seen_ids)
        expanded_points.extend(extra)

    sources: list[Source] = [
        _point_to_source(p, rank=i + 1) for i, p in enumerate(expanded_points)
    ]

    # Rerank ------------------------------------------------------------------
    if sources:
        sources = get_reranker().rerank(query, sources, top_n=final_top_n)

    retrieval_ms = int((time.monotonic() - t0) * 1000)
    meta = RetrievalMetadata(
        rewrittenQuery=f"{query}  [concepts: {', '.join(concepts)}]",
        embedding=settings.embedding_model,
        retrievalMs=retrieval_ms,
        collections=collections_hit,
        filter=f"books={effective_slugs}",
        topK=final_top_n,
        scoreThreshold=0.0,
        mode=(
            f"density (concepts={len(concepts)}, pool={pool}, "
            f"sections={len(final_sections)}, +adjacent +rerank)"
        ),
    )
    logger.info(
        "concept_density_search: %d concepts, %d candidates, "
        "%d sections selected, %d sources returned in %dms",
        len(concepts), len(candidates), len(final_sections), len(sources), retrieval_ms,
    )
    return sources, meta


class _PseudoPoint:
    """Lightweight stand-in for a Qdrant point so we can reuse
    :func:`_point_to_source` for sources we already converted earlier."""

    __slots__ = ("id", "score", "payload")

    def __init__(self, pid: str, score: float, payload: dict[str, Any]) -> None:
        self.id = pid
        self.score = score
        self.payload = payload


def _source_to_pseudo_point(src: Source) -> _PseudoPoint:
    """Round-trip a Source back into a point-like object so the second
    pass through ``_point_to_source`` reassigns ranks cleanly."""
    payload = {
        "book_slug": src.book,
        "book_name": src.book_name,
        "authors": src.authors,
        "year": src.year,
        "chapter_id": src.chapter,
        "section_id": src.section,
        "h2_path": src.title,
        "page_from": src.page_from,
        "page_to": src.page_to,
        "page": src.page,
        "text": src.chunk or src.excerpt or "",
    }
    return _PseudoPoint(src.chunkId, float(src.score), payload)
