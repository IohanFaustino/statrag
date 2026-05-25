"""T04 acceptance: cross-collection RRF (B5) + adjacent_sections expansion.

Tests:
1. Cross-collection RRF: points from different collections sort by within-collection
   rank, not by absolute Qdrant score (B5).
2. adjacent_sections=True post-processes results to include same-section neighbours.
3. adjacent_sections=False (default) leaves results untouched.
4. Empty source list short-circuits without Qdrant calls.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.chat import retrieval
from src.services.chat.schemas import Source


def _make_point(pid: str, payload: dict | None = None, score: float = 0.0):
    """Construct a minimal mock Qdrant point with id, payload, score."""
    p = SimpleNamespace()
    p.id = pid
    p.payload = payload or {}
    p.score = score
    return p


# ---------------------------------------------------------------------------
# B5: cross-collection RRF
# ---------------------------------------------------------------------------


def test_cross_collection_rrf_uses_within_collection_rank(monkeypatch):
    """B5 fix: scores in different collections are reciprocal-rank, not raw."""

    coll_a_points = [
        _make_point("a-1", payload={"book_slug": "a", "section_id": "1"}, score=0.95),
        _make_point("a-2", payload={"book_slug": "a", "section_id": "1"}, score=0.91),
    ]
    coll_b_points = [
        _make_point("b-1", payload={"book_slug": "b", "section_id": "1"}, score=0.10),
        _make_point("b-2", payload={"book_slug": "b", "section_id": "1"}, score=0.05),
    ]

    def _stub_query_collection(collection, *args, **kwargs):
        return coll_a_points if "a" in collection else coll_b_points

    monkeypatch.setattr(retrieval, "_query_collection", _stub_query_collection)
    monkeypatch.setattr(
        retrieval,
        "collections_for_books",
        lambda slugs: {"a_textbooks": ["a"], "b_textbooks": ["b"]},
    )
    monkeypatch.setattr(retrieval, "list_books", lambda: [SimpleNamespace(id="a"), SimpleNamespace(id="b")])
    monkeypatch.setattr(retrieval, "_embed_dense", lambda q: [0.0])
    monkeypatch.setattr(retrieval, "_embed_sparse", lambda q: SimpleNamespace(indices=[], values=[]))

    sources, _meta = retrieval.hybrid_search("q", book_slugs=["a", "b"], rerank=False)

    # Rank 1 from each collection should both have RRF score 1/60
    # so the result top-2 includes rank-1 from BOTH collections (not just the
    # one with higher raw Qdrant score).
    top_ids = [s.chunkId for s in sources]
    assert "a-1" in top_ids, f"top-K must include rank-1 from coll A: {top_ids}"
    assert "b-1" in top_ids, f"top-K must include rank-1 from coll B: {top_ids}"


# ---------------------------------------------------------------------------
# _expand_adjacent helper
# ---------------------------------------------------------------------------


def test_expand_adjacent_empty_sources_short_circuits():
    out = retrieval._expand_adjacent([], ["any_textbooks"])
    assert out == []


def test_expand_adjacent_empty_collections_short_circuits():
    src = Source(
        rank=1,
        book="a",
        chapter="ch1",
        section="2.1",
        title="t",
        excerpt="",
        score=0.5,
        chunkId="a-1",
        chunk="text",
        highlights=[],
    )
    out = retrieval._expand_adjacent([src], [])
    assert out == [src]


def test_expand_adjacent_appends_neighbours(monkeypatch):
    """Neighbouring chunks of same section get appended with new ranks."""
    src = Source(
        rank=1,
        book="a",
        chapter="ch1",
        section="2.1",
        title="t",
        excerpt="",
        score=0.5,
        chunkId="a-1",
        chunk="hit-text",
        highlights=[],
    )

    # Mock the Qdrant scroll result — 1 new neighbour + 1 already-seen point
    neighbour = _make_point(
        "a-2", payload={"book_slug": "a", "section_id": "2.1", "page_content": "neighbour-text",
                        "chapter_id": "ch1", "h2_path": "Hdr"},
        score=0.0,
    )
    duplicate = _make_point("a-1", payload={"book_slug": "a", "section_id": "2.1"}, score=0.0)

    fake_client = MagicMock()
    fake_client.scroll.return_value = ([neighbour, duplicate], None)

    monkeypatch.setattr(retrieval, "client", lambda: fake_client)

    out = retrieval._expand_adjacent([src], ["a_textbooks"])
    out_ids = [s.chunkId for s in out]
    assert "a-1" in out_ids  # original preserved
    assert "a-2" in out_ids  # new neighbour appended
    assert out.index(src) == 0, "original survivor stays at rank 1"
    appended = next(s for s in out if s.chunkId == "a-2")
    assert appended.rank > 1


def test_expand_adjacent_swallows_qdrant_errors(monkeypatch):
    src = Source(
        rank=1, book="a", chapter="ch1", section="2.1", title="t",
        excerpt="", score=0.5, chunkId="a-1", chunk="x", highlights=[],
    )
    fake_client = MagicMock()
    fake_client.scroll.side_effect = RuntimeError("qdrant down")
    monkeypatch.setattr(retrieval, "client", lambda: fake_client)

    out = retrieval._expand_adjacent([src], ["a_textbooks"])
    assert out == [src]  # original preserved, no crash


# ---------------------------------------------------------------------------
# adjacent_sections kwarg threads through hybrid_search
# ---------------------------------------------------------------------------


def test_hybrid_search_passes_adjacent_flag(monkeypatch):
    """When adjacent_sections=True, _expand_adjacent is called."""
    point = _make_point(
        "p-1", payload={"book_slug": "a", "section_id": "2.1", "page_content": "x"},
        score=0.5,
    )
    monkeypatch.setattr(retrieval, "_query_collection", lambda *a, **kw: [point])
    monkeypatch.setattr(retrieval, "collections_for_books", lambda slugs: {"a_textbooks": ["a"]})
    monkeypatch.setattr(retrieval, "list_books", lambda: [SimpleNamespace(id="a")])
    monkeypatch.setattr(retrieval, "_embed_dense", lambda q: [0.0])
    monkeypatch.setattr(retrieval, "_embed_sparse", lambda q: SimpleNamespace(indices=[], values=[]))

    called = {"hit": False}
    real_expand = retrieval._expand_adjacent

    def _spy(sources, collections):
        called["hit"] = True
        return sources

    monkeypatch.setattr(retrieval, "_expand_adjacent", _spy)
    retrieval.hybrid_search("q", book_slugs=["a"], rerank=False, adjacent_sections=True)
    assert called["hit"], "_expand_adjacent must be called when adjacent_sections=True"


def test_hybrid_search_default_does_not_expand(monkeypatch):
    point = _make_point(
        "p-1", payload={"book_slug": "a", "section_id": "2.1", "page_content": "x"},
        score=0.5,
    )
    monkeypatch.setattr(retrieval, "_query_collection", lambda *a, **kw: [point])
    monkeypatch.setattr(retrieval, "collections_for_books", lambda slugs: {"a_textbooks": ["a"]})
    monkeypatch.setattr(retrieval, "list_books", lambda: [SimpleNamespace(id="a")])
    monkeypatch.setattr(retrieval, "_embed_dense", lambda q: [0.0])
    monkeypatch.setattr(retrieval, "_embed_sparse", lambda q: SimpleNamespace(indices=[], values=[]))

    called = {"hit": False}

    def _spy(sources, collections):
        called["hit"] = True
        return sources

    monkeypatch.setattr(retrieval, "_expand_adjacent", _spy)
    retrieval.hybrid_search("q", book_slugs=["a"], rerank=False)  # no adjacent_sections
    assert not called["hit"], "_expand_adjacent must NOT be called by default"
