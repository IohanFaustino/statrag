"""Hybrid retriever for the chat service.

Executes Qdrant RRF (dense + sparse) queries and returns :class:`Source`
Pydantic objects — no LangChain dependency.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote


def _chart_url(payload: dict[str, Any]) -> str:
    """Build URL frontend can fetch. Prefer explicit url, else proxy by image_path."""
    explicit = payload.get("url") or payload.get("chart")
    if explicit:
        return explicit
    p = payload.get("image_path")
    if p:
        return f"/api/figures?path={quote(p, safe='')}"
    return ""

import openai as _openai
from fastapi import APIRouter
from fastembed import SparseTextEmbedding
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    Prefetch,
    SparseVector,
)

from src.core.config import settings
from src.core.qdrant_store import IMAGE_VECTOR, SPARSE_VECTOR, TEXT_VECTOR, client
from src.services.chat.books import collections_for_books, list_books
from src.services.chat.rerankers import get_reranker
from src.services.chat.schemas import Figure, HighlightRange, RetrievalMetadata, SearchRequest, Source

logger = logging.getLogger(__name__)

_SPARSE_MODEL = "Qdrant/bm25"

# Module-level sparse embedder (loaded once; ~200 MB model).
_sparse_embedder: SparseTextEmbedding | None = None


def _get_sparse_embedder() -> SparseTextEmbedding:
    global _sparse_embedder  # noqa: PLW0603
    if _sparse_embedder is None:
        _sparse_embedder = SparseTextEmbedding(model_name=_SPARSE_MODEL)
    return _sparse_embedder


def _embed_dense(query: str) -> list[float]:
    """Embed *query* with OpenAI text-embedding model; returns list[float]."""
    oa = _openai.OpenAI(api_key=settings.openai_api_key)
    resp = oa.embeddings.create(model=settings.embedding_model, input=query)
    return resp.data[0].embedding


def _embed_sparse(query: str) -> SparseVector:
    """Return a Qdrant :class:`SparseVector` for *query* using BM25."""
    embedder = _get_sparse_embedder()
    result = next(embedder.query_embed(query))
    return SparseVector(
        indices=result.indices.tolist(),
        values=result.values.tolist(),
    )


def _authors_short(authors_str: str) -> str:
    """T13-B: 'Smith et al.' form from a comma-joined full-name string.

    Args:
        authors_str: Comma-separated full names as written at ingest time.

    Returns:
        ``"Smith"`` for one author, ``"Smith et al."`` for two or more,
        ``""`` when input is empty.
    """
    if not authors_str:
        return ""
    names = [n.strip() for n in authors_str.split(",") if n.strip()]
    if not names:
        return ""
    first_surname = names[0].split()[-1] if names[0].split() else names[0]
    return f"{first_surname} et al." if len(names) > 1 else first_surname


def _safe_int(value: Any) -> int | None:
    """Return ``int(value)`` when possible, else ``None``. Ingestion uses ``-1``
    as a sentinel for "missing"; we map that to ``None`` so the LLM does not
    cite a negative page number."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def _point_to_source(point: Any, rank: int) -> Source:
    """Convert a raw Qdrant scored point to a :class:`Source` object.

    Maps ingestion payload (`h1`, `h2_path`, `section_id`, `chapter_id`,
    `page_from`/`page_to`, `book_slug`, `book_name`, `authors`, `year`,
    `text`, `synopsis`) into the UI's Source schema. Last segment of
    `h2_path` (split by ` | `) is used as the section label; the full path
    becomes the title.

    T13-B: surfaces book_name, authors (+authors_short), year, and the
    page_from/page_to range. These fields drive APA-style inline citations.
    """
    payload: dict[str, Any] = point.payload or {}
    text: str = payload.get("text", "")
    h2_path: str = (
        payload.get("h2_path")
        or payload.get("section_path")
        or payload.get("section")
        or ""
    )
    h1: str = payload.get("h1") or ""
    if h2_path:
        last_segment = h2_path.split(" | ")[-1].strip()
        section = last_segment or h2_path
        title = h2_path
    else:
        section = "§?"
        title = h1 or payload.get("section_title") or payload.get("title") or ""

    # Pages — T13-B: keep both the legacy single ``page`` value AND the full
    # page_from/page_to range so callers can render "p. 15-18" citations.
    page_from = _safe_int(payload.get("page_from"))
    page_to = _safe_int(payload.get("page_to"))
    page = _safe_int(payload.get("page")) or page_from

    # Authors — ingestion writes a comma-joined string. We keep that as-is on
    # ``authors`` and compute the "Smith et al." display form once.
    authors = str(payload.get("authors", "") or "")

    return Source(
        rank=rank,
        book=payload.get("book_slug", ""),
        chapter=payload.get("chapter_id", ""),
        section=section,
        title=title,
        excerpt=text[:200],
        score=float(point.score),
        page=page,
        chunkId=str(point.id),
        chunk=text,
        highlights=[],
        book_name=str(payload.get("book_name", "") or ""),
        authors=authors,
        authors_short=_authors_short(authors),
        year=_safe_int(payload.get("year")),
        page_from=page_from,
        page_to=page_to,
    )


def _build_filter(slugs: list[str]) -> Filter | None:
    """Build a Qdrant payload filter matching any of *slugs*."""
    if not slugs:
        return None
    return Filter(
        must=[
            FieldCondition(key="book_slug", match=MatchAny(any=slugs)),
        ]
    )


def _query_collection(
    collection: str,
    dense_vec: list[float],
    sparse_vec: SparseVector,
    top_k: int,
    payload_filter: Filter | None,
) -> list[Any]:
    """Run RRF hybrid query against *collection* and return raw points."""
    try:
        res = client().query_points(
            collection_name=collection,
            prefetch=[
                Prefetch(query=dense_vec, using=TEXT_VECTOR, limit=top_k * 4),
                Prefetch(query=sparse_vec, using=SPARSE_VECTOR, limit=top_k * 4),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            query_filter=payload_filter,
            with_payload=True,
        )
        return list(res.points)
    except Exception:  # noqa: BLE001
        logger.exception("Qdrant query failed for collection %r", collection)
        return []


def _expand_adjacent(sources: list[Source], collections: list[str]) -> list[Source]:
    """For each unique section in *sources*, fetch any other chunks belonging to
    that same section and append them (deduplicated by chunkId) at the tail.

    T04: wires the previously-dead ``RetrievalFlags.adjacent_sections`` flag.
    The original hit ranking is preserved; appended chunks follow with their
    own incrementing ``rank``. Each appended chunk inherits a small score so it
    sorts below the retrieved survivors without disturbing reranker output.

    Args:
        sources: Source list to expand. Returned list is a new list; input is
            not mutated.
        collections: Collection names to scan for neighbouring chunks.

    Returns:
        A new list of sources with same-section neighbours appended.
    """
    if not sources or not collections:
        return sources

    seen_ids: set[str] = {s.chunkId for s in sources}
    # Group keys by (book_slug, section_id) — we want to fetch *all* chunks of
    # those sections and append the new ones.
    section_keys: set[tuple[str, str]] = {(s.book, s.section) for s in sources}
    out: list[Source] = list(sources)
    next_rank = len(out) + 1
    appended_score = 0.001  # tiny — never outranks an actual hit

    for book_slug, section_id in section_keys:
        flt = Filter(
            must=[
                FieldCondition(key="book_slug", match=MatchAny(any=[book_slug])),
                FieldCondition(key="section_id", match=MatchAny(any=[section_id])),
            ]
        )
        for collection in collections:
            try:
                res = client().scroll(
                    collection_name=collection,
                    scroll_filter=flt,
                    limit=20,
                    with_payload=True,
                )
                points = res[0]
            except Exception:  # noqa: BLE001
                continue
            for p in points:
                pid = str(p.id)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                # Wrap as Source — reuse _point_to_source contract
                p.score = appended_score  # noqa: F841 — mutate in place to feed _point_to_source
                src = _point_to_source(p, rank=next_rank)
                next_rank += 1
                out.append(src)
    return out


def fetch_chapter_sections(
    book_slug: str,
    chapter_id: str,
    *,
    max_sections: int = 200,
) -> list[Source]:
    """Scroll every chunk of one chapter and return them in chapter order.

    Order is structural: sort by ``(page_from, section_id)`` so the reading
    sequence (and the author's build-of-ideas) is preserved. No embeddings,
    no relevance scoring — this is a metadata fetch, not a search.

    Args:
        book_slug: Book slug (e.g. ``"islp"``).
        chapter_id: Chapter id (e.g. ``"ch02"``).
        max_sections: Hard cap on chunks scrolled.

    Returns:
        Ordered ``Source`` list (may be empty when the chapter is unknown).
    """
    collection_map = collections_for_books([book_slug])
    flt = Filter(
        must=[
            FieldCondition(key="book_slug", match=MatchAny(any=[book_slug])),
            FieldCondition(key="chapter_id", match=MatchAny(any=[chapter_id])),
        ]
    )
    raw: list[Any] = []
    for collection in collection_map:
        try:
            points, _ = client().scroll(
                collection_name=collection,
                scroll_filter=flt,
                limit=max_sections,
                with_payload=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("chapter scroll failed for %r", collection)
            continue
        raw.extend(points)

    def _order_key(p: Any) -> tuple[int, str]:
        payload = p.payload or {}
        pf = _safe_int(payload.get("page_from"))
        return (pf if pf is not None else 10**9, str(payload.get("section_id", "")))

    raw.sort(key=_order_key)
    out: list[Source] = []
    for i, p in enumerate(raw[:max_sections]):
        # scroll() returns Record objects with no `.score`; _point_to_source
        # reads point.score, so seed a neutral score (mirrors _expand_adjacent).
        p.score = 0.0  # noqa: F841 — mutate in place to feed _point_to_source
        out.append(_point_to_source(p, rank=i + 1))
    return out


def hybrid_search(
    query: str,
    *,
    book_slugs: list[str] | None = None,
    top_k: int = 5,
    rerank: bool = False,
    rerank_top_n: int | None = None,
    adjacent_sections: bool = False,
) -> tuple[list[Source], RetrievalMetadata]:
    """Hybrid dense+sparse RRF search over Qdrant section-level chunks.

    Args:
        query: User query string.
        book_slugs: Optional list of book slugs to restrict the search.
            When *None*, all books from the registry are searched.
        top_k: Maximum number of sources to return (ignored when rerank=True;
            see rerank_top_n instead).
        rerank: When True, fetch ``settings.rerank_top_k_in`` candidates from
            RRF then rerank with the cross-encoder, returning the top
            ``rerank_top_n or settings.rerank_top_n_out`` sources.
        rerank_top_n: Override for the number of sources returned after
            reranking.  Defaults to ``settings.rerank_top_n_out``.

    Returns:
        A tuple of (sources, metadata) where sources are sorted by score
        (highest first) and assigned 1-indexed ranks.
    """
    t0 = time.monotonic()

    # Resolve book groups --------------------------------------------------
    effective_slugs: list[str] | None = book_slugs
    if effective_slugs is None:
        effective_slugs = [b.id for b in list_books()]

    # collections_for_books returns {"<field>_textbooks": [slug, ...]}
    collection_map: dict[str, list[str]] = collections_for_books(effective_slugs)

    # When reranking, fetch a wider candidate set from Qdrant.
    fetch_k = settings.rerank_top_k_in if rerank else top_k

    # Produce embeddings once ----------------------------------------------
    dense_vec = _embed_dense(query)
    sparse_vec = _embed_sparse(query)

    # Query each collection -------------------------------------------------
    # T04 (B5) fix: per-collection RRF scores are not comparable across
    # collections (each pool has its own internal distribution). After
    # fetching, replace each point's score with a Reciprocal Rank Fusion
    # value of its within-collection rank (k=60 is the canonical RRF
    # constant). This produces a single comparable scale across collections.
    all_points: list[Any] = []
    collections_hit: list[str] = []
    filter_desc_parts: list[str] = []

    for collection, slugs in collection_map.items():
        payload_filter = _build_filter(slugs)
        points = _query_collection(
            collection, dense_vec, sparse_vec, fetch_k, payload_filter
        )
        for rank_in_coll, point in enumerate(points):
            point.score = 1.0 / (60.0 + rank_in_coll)
            all_points.append(point)
        collections_hit.append(collection)
        filter_desc_parts.append(f"{collection}[{', '.join(slugs)}]")

    all_points.sort(key=lambda p: p.score, reverse=True)
    top_points = all_points[:fetch_k]

    sources: list[Source] = [
        _point_to_source(p, rank=i + 1) for i, p in enumerate(top_points)
    ]

    # Optional cross-encoder reranking -------------------------------------
    if rerank:
        top_n = rerank_top_n or settings.rerank_top_n_out
        sources = get_reranker().rerank(query, sources, top_n=top_n)
        mode_str = "hybrid (RRF: dense + sparse) + rerank=bge-reranker-v2-m3"
        effective_top_k = top_n
    else:
        # Trim to requested top_k on the non-rerank path (fetch_k == top_k here).
        sources = sources[:top_k]
        mode_str = "hybrid (RRF: dense + sparse)"
        effective_top_k = top_k

    # T04: optional same-section adjacent-chunk expansion.
    if adjacent_sections and sources:
        sources = _expand_adjacent(sources, collections_hit)
        mode_str = mode_str + " + adjacent_sections"

    retrieval_ms = int((time.monotonic() - t0) * 1000)

    filter_str = "; ".join(filter_desc_parts) if filter_desc_parts else "none"
    metadata = RetrievalMetadata(
        rewrittenQuery=query,
        embedding=settings.embedding_model,
        retrievalMs=retrieval_ms,
        collections=collections_hit,
        filter=filter_str,
        topK=effective_top_k,
        scoreThreshold=0.0,
        mode=mode_str,
    )

    logger.info(
        "hybrid_search: %d sources from %d collections in %dms (rerank=%s)",
        len(sources),
        len(collections_hit),
        retrieval_ms,
        rerank,
    )
    return sources, metadata


async def async_hybrid_search(
    query: str,
    *,
    book_slugs: list[str] | None = None,
    top_k: int = 5,
    rerank: bool = False,
    rerank_top_n: int | None = None,
    adjacent_sections: bool = False,
) -> tuple[list[Source], RetrievalMetadata]:
    """Async wrapper around the synchronous :func:`hybrid_search`.

    Runs the blocking call in a thread so it can be awaited from async contexts.

    Args:
        query: User query string.
        book_slugs: Optional list of book slugs to restrict the search.
        top_k: Maximum number of sources to return.
        rerank: When True, apply cross-encoder reranking.
        rerank_top_n: Override for the number of sources returned after reranking.

    Returns:
        A tuple of (sources, metadata).
    """
    return await asyncio.to_thread(
        hybrid_search,
        query,
        book_slugs=book_slugs,
        top_k=top_k,
        rerank=rerank,
        rerank_top_n=rerank_top_n,
        adjacent_sections=adjacent_sections,
    )


async def multi_query_hybrid_search(
    queries: list[str],
    *,
    book_slugs: list[str] | None = None,
    top_k: int = 5,
    rerank: bool = False,
    rerank_top_n: int | None = None,
    adjacent_sections: bool = False,
) -> tuple[list[Source], RetrievalMetadata]:
    """Run hybrid search over multiple queries, merge and dedup by chunkId.

    Executes :func:`hybrid_search` for each query in *queries* in parallel
    (via ``asyncio.to_thread``), then:

    1. Merges all results, keeping the highest score per ``chunkId``.
    2. Re-sorts the merged set by score descending, truncates to *top_k*
       (or ``settings.rerank_top_k_in`` when reranking).
    3. If *rerank* is ``True``, runs the cross-encoder **once** on the merged
       set, using *queries[0]* as the rerank pivot query.
    4. Returns a single :class:`RetrievalMetadata` with:
       - ``rewrittenQuery``: ``" | ".join(queries)`` (truncated to 300 chars).
       - ``collections``: union of all collections hit across all queries.

    Args:
        queries: One or more query strings.  Must be non-empty.
        book_slugs: Optional list of book slugs to restrict the search.
        top_k: Maximum sources to return (non-rerank path).
        rerank: When True, apply cross-encoder reranking on the merged set.
        rerank_top_n: Override for sources kept after reranking.

    Returns:
        A tuple of (sources, metadata).

    Raises:
        ValueError: If *queries* is empty.
    """
    if not queries:
        raise ValueError("queries must be non-empty")

    # Short-circuit: single query uses the plain path (no parallel overhead).
    if len(queries) == 1:
        return await async_hybrid_search(
            queries[0],
            book_slugs=book_slugs,
            top_k=top_k,
            rerank=rerank,
            rerank_top_n=rerank_top_n,
            adjacent_sections=adjacent_sections,
        )

    t0 = time.monotonic()

    # Run all queries in parallel; each call is blocking but runs in a thread.
    tasks = [
        asyncio.to_thread(
            hybrid_search,
            q,
            book_slugs=book_slugs,
            top_k=top_k,
            rerank=False,  # rerank once on the merged set below
            rerank_top_n=None,
        )
        for q in queries
    ]
    results: list[tuple[list[Source], RetrievalMetadata]] = await asyncio.gather(*tasks)

    # Merge: keep highest score per chunkId.
    best_by_chunk: dict[str, Source] = {}
    all_collections: list[str] = []
    for sources_i, meta_i in results:
        all_collections.extend(meta_i.collections)
        for src in sources_i:
            existing = best_by_chunk.get(src.chunkId)
            if existing is None or src.score > existing.score:
                best_by_chunk[src.chunkId] = src

    # Sorted by score descending.
    merged: list[Source] = sorted(
        best_by_chunk.values(), key=lambda s: s.score, reverse=True
    )

    # Determine the candidate set size.
    fetch_k = settings.rerank_top_k_in if rerank else top_k
    candidates = merged[:fetch_k]

    # Optional cross-encoder reranking — pivot on the first (original) query.
    if rerank and candidates:
        top_n = rerank_top_n or settings.rerank_top_n_out
        candidates = get_reranker().rerank(queries[0], candidates, top_n=top_n)
        mode_str = "multi-query hybrid (RRF: dense + sparse) + rerank=bge-reranker-v2-m3"
        effective_top_k = top_n
    else:
        candidates = candidates[:top_k]
        mode_str = "multi-query hybrid (RRF: dense + sparse)"
        effective_top_k = top_k

    # T04: same-section neighbour expansion (multi-query path).
    if adjacent_sections and candidates:
        candidates = _expand_adjacent(candidates, list(set(all_collections)))
        mode_str = mode_str + " + adjacent_sections"

    # Re-assign sequential 1-indexed ranks.
    for i, src in enumerate(candidates):
        src.rank = i + 1

    retrieval_ms = int((time.monotonic() - t0) * 1000)

    # Deduplicate collection list preserving order.
    seen_cols: set[str] = set()
    unique_collections: list[str] = []
    for col in all_collections:
        if col not in seen_cols:
            seen_cols.add(col)
            unique_collections.append(col)

    merged_query = " | ".join(queries)[:300]
    metadata = RetrievalMetadata(
        rewrittenQuery=merged_query,
        embedding=settings.embedding_model,
        retrievalMs=retrieval_ms,
        collections=unique_collections,
        filter="multi-query",
        topK=effective_top_k,
        scoreThreshold=0.0,
        mode=mode_str,
    )

    logger.info(
        "multi_query_hybrid_search: %d queries → %d merged sources in %dms (rerank=%s)",
        len(queries),
        len(candidates),
        retrieval_ms,
        rerank,
    )
    return candidates, metadata


def search_figures(
    query: str,
    book_slugs: list[str] | None = None,
    k: int = 5,
) -> list[Figure]:
    """Search image collections for figures matching *query*.

    Args:
        query: User query string.
        book_slugs: Optional list of book slugs to restrict the search.
            When *None*, all books are searched.
        k: Maximum number of figures to return.

    Returns:
        List of :class:`Figure` objects ordered by similarity score.
    """
    effective_slugs: list[str] | None = book_slugs
    if effective_slugs is None:
        effective_slugs = [b.id for b in list_books()]

    collection_map: dict[str, list[str]] = collections_for_books(effective_slugs)

    # Filter to only image collections that actually exist (avoid 404 spam)
    existing: set[str] = set()
    try:
        existing = {c.name for c in client().get_collections().collections}
    except Exception:  # noqa: BLE001
        pass

    image_targets: list[tuple[str, list[str]]] = []
    for text_collection, slugs in collection_map.items():
        image_collection = text_collection.replace("_textbooks", "_images")
        if image_collection in existing:
            image_targets.append((image_collection, slugs))

    figures: list[Figure] = []
    if not image_targets:
        return figures

    dense_vec = _embed_dense(query)

    for image_collection, slugs in image_targets:
        payload_filter = _build_filter(slugs)
        try:
            res = client().query_points(
                collection_name=image_collection,
                query=dense_vec,
                using=IMAGE_VECTOR,
                limit=k,
                query_filter=payload_filter,
                with_payload=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Qdrant figure query failed for collection %r", image_collection
            )
            continue

        for p in res.points:
            payload: dict[str, Any] = p.payload or {}
            figures.append(
                Figure(
                    ref=payload.get("ref") or payload.get("figure_id") or str(p.id),
                    book=payload.get("book_slug", ""),
                    chapter=payload.get("chapter_id", ""),
                    caption=payload.get("caption") or payload.get("text") or "",
                    chart=_chart_url(payload),
                )
            )

    # Sort by natural insertion order (already score-sorted per collection);
    # global re-rank is not possible without returning scores from Figure.
    return figures[:k]


def search_figures_with_scores(
    query: str,
    book_slugs: list[str] | None = None,
    k: int = 5,
) -> list[tuple[Figure, float]]:
    """Search image collections for figures and return (figure, score) pairs.

    Identical logic to :func:`search_figures` but preserves the Qdrant
    similarity score alongside each figure so the vision gate can apply its
    thresholds.  The existing :func:`search_figures` signature is unchanged to
    avoid breaking downstream callers.

    Args:
        query: User query string.
        book_slugs: Optional list of book slugs to restrict the search.
            When *None*, all books are searched.
        k: Maximum number of figures to return.

    Returns:
        List of ``(Figure, score)`` tuples ordered by similarity score
        (highest first), truncated to *k*.
    """
    effective_slugs: list[str] | None = book_slugs
    if effective_slugs is None:
        effective_slugs = [b.id for b in list_books()]

    collection_map: dict[str, list[str]] = collections_for_books(effective_slugs)

    existing: set[str] = set()
    try:
        existing = {c.name for c in client().get_collections().collections}
    except Exception:  # noqa: BLE001
        pass

    image_targets: list[tuple[str, list[str]]] = []
    for text_collection, slugs in collection_map.items():
        image_collection = text_collection.replace("_textbooks", "_images")
        if image_collection in existing:
            image_targets.append((image_collection, slugs))

    pairs: list[tuple[Figure, float]] = []
    if not image_targets:
        return pairs

    dense_vec = _embed_dense(query)

    for image_collection, slugs in image_targets:
        payload_filter = _build_filter(slugs)
        try:
            res = client().query_points(
                collection_name=image_collection,
                query=dense_vec,
                using=IMAGE_VECTOR,
                limit=k,
                query_filter=payload_filter,
                with_payload=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Qdrant figure query failed for collection %r", image_collection
            )
            continue

        for p in res.points:
            payload: dict[str, Any] = p.payload or {}
            fig = Figure(
                ref=payload.get("ref") or payload.get("figure_id") or str(p.id),
                book=payload.get("book_slug", ""),
                chapter=payload.get("chapter_id", ""),
                caption=payload.get("caption") or payload.get("text") or "",
                chart=_chart_url(payload),
            )
            pairs.append((fig, float(p.score)))

    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs[:k]


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.post("/search")
def route_search(req: SearchRequest) -> dict:
    """Hybrid search endpoint.

    Returns a JSON object with ``sources``, ``figures``, and ``metadata``.
    """
    sources, metadata = hybrid_search(
        req.query,
        book_slugs=req.books,
        top_k=req.topK,
    )
    figures = search_figures(req.query, book_slugs=req.books, k=5)

    return {
        "sources": [s.model_dump() for s in sources],
        "figures": [f.model_dump() for f in figures],
        "metadata": metadata.model_dump(),
    }
