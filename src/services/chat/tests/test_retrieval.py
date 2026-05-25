"""Tests for src.services.chat.retrieval and src.services.chat.highlights.

All external I/O (Qdrant, OpenAI) is mocked so tests run fully offline.
"""
from __future__ import annotations

import math
import os
import sys
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on PYTHONPATH and dummy API key is set
_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_point(
    book_slug: str = "islp",
    chapter_id: str = "ch02",
    score: float = 0.9,
    text: str = "This is a test chunk about linear regression.",
) -> SimpleNamespace:
    """Create a fake Qdrant ScoredPoint-like namespace."""
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        score=score,
        payload={
            "book_slug": book_slug,
            "chapter_id": chapter_id,
            "section_path": "2.1 Overview",
            "section_title": "Overview",
            "text": text,
            "page": 42,
        },
    )


def _fake_dense_embedding(query: str) -> list[float]:  # noqa: ARG001
    """Return a deterministic 3072-d unit vector."""
    v = [0.0] * 3072
    v[0] = 1.0
    return v


def _fake_sparse_embedding() -> Any:
    """Return a fake fastembed SparseEmbedding-like object."""
    import numpy as np  # noqa: PLC0415

    return SimpleNamespace(
        indices=np.array([0, 5, 10], dtype=np.int32),
        values=np.array([0.5, 0.3, 0.2], dtype=np.float32),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_qdrant_client():
    """Return a mock Qdrant client that yields two fake scored points."""
    points = [_make_point(score=0.95), _make_point(score=0.80)]
    result = SimpleNamespace(points=points)

    mock_client = MagicMock()
    mock_client.query_points.return_value = result
    return mock_client


@pytest.fixture
def patch_embeddings(monkeypatch: pytest.MonkeyPatch):
    """Patch OpenAI embeddings and fastembed sparse embedder."""
    # Patch _embed_dense in the retrieval module
    monkeypatch.setattr(
        "src.services.chat.retrieval._embed_dense",
        _fake_dense_embedding,
    )
    # Patch _get_sparse_embedder to return a stub
    fake_sparse = MagicMock()
    fake_sparse.query_embed.return_value = iter([_fake_sparse_embedding()])
    monkeypatch.setattr(
        "src.services.chat.retrieval._get_sparse_embedder",
        lambda: fake_sparse,
    )


@pytest.fixture
def patch_qdrant(monkeypatch: pytest.MonkeyPatch, fake_qdrant_client: MagicMock):
    """Replace the module-level Qdrant client() function."""
    monkeypatch.setattr(
        "src.services.chat.retrieval.client",
        lambda: fake_qdrant_client,
    )
    return fake_qdrant_client


# ---------------------------------------------------------------------------
# Tests — hybrid_search shape
# ---------------------------------------------------------------------------

class TestHybridSearch:
    def test_returns_sources_and_metadata(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """hybrid_search should return (list[Source], RetrievalMetadata)."""
        from src.services.chat.retrieval import hybrid_search
        from src.services.chat.schemas import RetrievalMetadata, Source

        sources, meta = hybrid_search("what is linear regression?", book_slugs=["islp"], top_k=5)

        assert isinstance(sources, list)
        assert isinstance(meta, RetrievalMetadata)

    def test_source_count_bounded_by_top_k(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Number of returned sources must not exceed top_k."""
        from src.services.chat.retrieval import hybrid_search

        sources, _ = hybrid_search("regression", book_slugs=["islp"], top_k=5)
        assert len(sources) <= 5

    def test_sources_have_correct_types(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Each Source must have the required fields with correct types."""
        from src.services.chat.retrieval import hybrid_search
        from src.services.chat.schemas import Source

        sources, _ = hybrid_search("regression", book_slugs=["islp"], top_k=5)
        for src in sources:
            assert isinstance(src, Source)
            assert isinstance(src.rank, int)
            assert src.rank >= 1
            assert isinstance(src.book, str)
            assert isinstance(src.chapter, str)
            assert isinstance(src.score, float)
            assert isinstance(src.chunkId, str)
            assert isinstance(src.chunk, str)
            assert isinstance(src.highlights, list)

    def test_ranks_are_one_indexed_and_sequential(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Ranks should start at 1 and increase by 1."""
        from src.services.chat.retrieval import hybrid_search

        sources, _ = hybrid_search("test", book_slugs=["islp"], top_k=5)
        for expected_rank, src in enumerate(sources, start=1):
            assert src.rank == expected_rank

    def test_sources_sorted_by_score_descending(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Sources must be ordered by score, highest first."""
        from src.services.chat.retrieval import hybrid_search

        sources, _ = hybrid_search("test", book_slugs=["islp"], top_k=5)
        scores = [s.score for s in sources]
        assert scores == sorted(scores, reverse=True)

    def test_metadata_fields_populated(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """RetrievalMetadata should carry expected field values."""
        from src.services.chat.retrieval import hybrid_search

        _, meta = hybrid_search("test query", book_slugs=["islp"], top_k=3)
        assert meta.topK == 3
        assert meta.scoreThreshold == 0.0
        assert "RRF" in meta.mode
        assert meta.retrievalMs >= 0
        assert isinstance(meta.collections, list)
        assert meta.rewrittenQuery == "test query"

    def test_excerpt_max_200_chars(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Source.excerpt must be at most 200 characters."""
        from src.services.chat.retrieval import hybrid_search

        sources, _ = hybrid_search("test", book_slugs=["islp"], top_k=5)
        for src in sources:
            assert len(src.excerpt) <= 200

    def test_page_extracted_from_payload(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """Source.page should be populated when the payload includes it."""
        from src.services.chat.retrieval import hybrid_search

        sources, _ = hybrid_search("test", book_slugs=["islp"], top_k=5)
        # The fake points include page=42
        for src in sources:
            assert src.page == 42

    def test_no_book_slugs_uses_all_books(
        self,
        patch_embeddings: None,
        patch_qdrant: MagicMock,
    ) -> None:
        """hybrid_search(book_slugs=None) should still return sources."""
        from src.services.chat.retrieval import hybrid_search

        sources, meta = hybrid_search("statistics", book_slugs=None, top_k=5)
        assert isinstance(sources, list)
        assert isinstance(meta.collections, list)


# ---------------------------------------------------------------------------
# Tests — compute_highlights
# ---------------------------------------------------------------------------

class TestComputeHighlights:
    def test_returns_list(self) -> None:
        """compute_highlights must always return a list."""
        from src.services.chat.highlights import compute_highlights

        with patch("src.services.chat.highlights._embed_batch") as mock_emb:
            mock_emb.return_value = [[1.0] + [0.0] * 3071] * 10
            result = compute_highlights("regression", "Short text.")
        assert isinstance(result, list)

    def test_empty_chunk_returns_empty(self) -> None:
        """Empty chunk should return an empty list without any API call."""
        from src.services.chat.highlights import compute_highlights

        with patch("src.services.chat.highlights._embed_batch") as mock_emb:
            result = compute_highlights("query", "")
        mock_emb.assert_not_called()
        assert result == []

    def test_short_chunk_returns_full_range(self) -> None:
        """A chunk with ≤ 2 sentences should return the full-chunk range."""
        from src.services.chat.highlights import HighlightRange, compute_highlights

        chunk = "Only one sentence here."
        with patch("src.services.chat.highlights._embed_batch") as mock_emb:
            result = compute_highlights("query", chunk)
        mock_emb.assert_not_called()
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == len(chunk)

    def test_two_sentence_chunk_returns_full_range(self) -> None:
        """A chunk with exactly 2 sentences should also use full-chunk range."""
        from src.services.chat.highlights import compute_highlights

        chunk = "First sentence here. Second sentence here."
        with patch("src.services.chat.highlights._embed_batch") as mock_emb:
            result = compute_highlights("query", chunk)
        mock_emb.assert_not_called()
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == len(chunk)

    def test_multi_sentence_calls_embed_api(self) -> None:
        """A chunk with >2 sentences should invoke _embed_batch."""
        from src.services.chat.highlights import compute_highlights

        chunk = (
            "Linear regression fits a line to data. "
            "The coefficients are estimated by OLS. "
            "Residuals should be normally distributed. "
            "Model fit is measured by R-squared."
        )
        dim = 3072
        # Query embedding + 4 sentence embeddings, all pointing the same direction
        embs = [[1.0] + [0.0] * (dim - 1)] * 5

        with patch("src.services.chat.highlights._embed_batch", return_value=embs) as mock_emb:
            result = compute_highlights("regression coefficients", chunk, max_spans=2)

        mock_emb.assert_called_once()
        assert isinstance(result, list)
        for span in result:
            assert span.start >= 0
            assert span.end <= len(chunk)
            assert span.end > span.start

    def test_highlight_count_bounded_by_max_spans(self) -> None:
        """Number of highlights must not exceed max_spans."""
        from src.services.chat.highlights import compute_highlights

        chunk = (
            "Sentence one about probability. "
            "Sentence two about statistics. "
            "Sentence three about regression. "
            "Sentence four about inference."
        )
        dim = 3072
        embs = [[1.0] + [0.0] * (dim - 1)] * 5

        with patch("src.services.chat.highlights._embed_batch", return_value=embs):
            result = compute_highlights("probability", chunk, max_spans=2)

        assert len(result) <= 2

    def test_result_type_is_highlight_range(self) -> None:
        """All returned items must be HighlightRange instances."""
        from src.services.chat.highlights import HighlightRange, compute_highlights

        chunk = (
            "Regression minimizes squared errors. "
            "The loss function is convex. "
            "Gradient descent converges to optimum."
        )
        dim = 3072
        embs = [[1.0] + [0.0] * (dim - 1)] * 4

        with patch("src.services.chat.highlights._embed_batch", return_value=embs):
            result = compute_highlights("gradient descent", chunk)

        for item in result:
            assert isinstance(item, HighlightRange)

    def test_low_similarity_returns_no_highlights(self) -> None:
        """Sentences with cosine similarity <= 0.5 should be excluded."""
        from src.services.chat.highlights import compute_highlights

        chunk = (
            "First unrelated sentence. "
            "Second unrelated sentence. "
            "Third unrelated sentence."
        )
        dim = 3072
        # Query points in direction [1, 0, 0, ...]; sentences in orthogonal direction
        query_emb = [1.0] + [0.0] * (dim - 1)
        sent_emb = [0.0, 1.0] + [0.0] * (dim - 2)  # cosine = 0 with query
        embs = [query_emb] + [sent_emb] * 3

        with patch("src.services.chat.highlights._embed_batch", return_value=embs):
            result = compute_highlights("query", chunk)

        assert result == []


# ---------------------------------------------------------------------------
# Tests — multi_query_hybrid_search
# ---------------------------------------------------------------------------


class TestMultiQueryHybridSearch:
    """Test multi_query_hybrid_search with mocked Qdrant and embeddings."""

    @pytest.fixture
    def patch_embeddings(self, monkeypatch: pytest.MonkeyPatch):
        """Patch dense + sparse embedders in the retrieval module.

        The sparse embedder uses ``side_effect`` so that each call to
        ``query_embed`` returns a fresh single-item iterator, avoiding the
        ``StopIteration`` that would otherwise occur when two threads each
        call the same mock sequentially.
        """
        monkeypatch.setattr(
            "src.services.chat.retrieval._embed_dense",
            _fake_dense_embedding,
        )
        fake_sparse = MagicMock()
        # Return a brand-new iterator on every call to query_embed
        fake_sparse.query_embed.side_effect = lambda _q: iter([_fake_sparse_embedding()])
        monkeypatch.setattr(
            "src.services.chat.retrieval._get_sparse_embedder",
            lambda: fake_sparse,
        )

    def _make_qdrant_client(self, points_list: list) -> MagicMock:
        """Return a mock Qdrant client yielding *points_list* from query_points."""
        result = SimpleNamespace(points=points_list)
        mock = MagicMock()
        mock.query_points.return_value = result
        return mock

    @pytest.mark.asyncio
    async def test_dedup_by_chunk_id(
        self,
        patch_embeddings: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Chunks returned by multiple queries must be deduped by chunkId; highest score kept."""
        shared_id = str(uuid.uuid4())

        # Query 1 returns the shared chunk at score=0.9 + a unique chunk
        chunk_q1_shared = SimpleNamespace(
            id=shared_id,
            score=0.9,
            payload={
                "book_slug": "islp",
                "chapter_id": "ch01",
                "section_path": "1.1 Shared",
                "text": "Shared chunk text.",
                "page": 10,
            },
        )
        chunk_q1_unique = _make_point(book_slug="islp", score=0.7, text="Unique to Q1.")

        # Query 2 returns the same shared chunk at a LOWER score + its own unique chunk
        chunk_q2_shared = SimpleNamespace(
            id=shared_id,
            score=0.5,  # lower — should be discarded in favour of 0.9
            payload={
                "book_slug": "islp",
                "chapter_id": "ch01",
                "section_path": "1.1 Shared",
                "text": "Shared chunk text.",
                "page": 10,
            },
        )
        chunk_q2_unique = _make_point(book_slug="islp", score=0.6, text="Unique to Q2.")

        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(points=[chunk_q1_shared, chunk_q1_unique])
            return SimpleNamespace(points=[chunk_q2_shared, chunk_q2_unique])

        mock_client = MagicMock()
        mock_client.query_points.side_effect = _side_effect
        monkeypatch.setattr("src.services.chat.retrieval.client", lambda: mock_client)

        from src.services.chat.retrieval import multi_query_hybrid_search

        sources, metadata = await multi_query_hybrid_search(
            ["what is linear regression?", "explain OLS"],
            book_slugs=["islp"],
            top_k=5,
        )

        # chunkId dedup: the shared chunk must appear exactly once
        chunk_ids = [s.chunkId for s in sources]
        assert chunk_ids.count(shared_id) == 1, "shared chunk must appear exactly once"

        # T04 (B5 fix): scores are now Reciprocal-Rank-Fusion values, not raw
        # Qdrant scores. The shared chunk appears at rank 0 in both queries, so
        # its RRF score is 1/(60+0) = 1/60.
        shared_src = next(s for s in sources if s.chunkId == shared_id)
        assert shared_src.score == pytest.approx(1.0 / 60.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_ranks_are_sequential(
        self,
        patch_embeddings: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After merging, ranks must be 1-indexed and sequential."""
        points = [_make_point(score=0.9), _make_point(score=0.7)]
        mock_client = MagicMock()
        mock_client.query_points.return_value = SimpleNamespace(points=points)
        monkeypatch.setattr("src.services.chat.retrieval.client", lambda: mock_client)

        from src.services.chat.retrieval import multi_query_hybrid_search

        sources, _ = await multi_query_hybrid_search(
            ["query one", "query two"],
            book_slugs=["islp"],
            top_k=5,
        )

        for expected, src in enumerate(sources, start=1):
            assert src.rank == expected

    @pytest.mark.asyncio
    async def test_metadata_rewritten_query_joined(
        self,
        patch_embeddings: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RetrievalMetadata.rewrittenQuery must be the pipe-joined query list."""
        mock_client = MagicMock()
        mock_client.query_points.return_value = SimpleNamespace(points=[_make_point()])
        monkeypatch.setattr("src.services.chat.retrieval.client", lambda: mock_client)

        from src.services.chat.retrieval import multi_query_hybrid_search

        queries = ["ridge regression", "L2 penalty"]
        _, metadata = await multi_query_hybrid_search(
            queries,
            book_slugs=["islp"],
            top_k=5,
        )

        assert metadata.rewrittenQuery == "ridge regression | L2 penalty"

    @pytest.mark.asyncio
    async def test_single_query_delegates_to_async_hybrid_search(
        self,
        patch_embeddings: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A single-element query list must still return valid (sources, metadata)."""
        mock_client = MagicMock()
        mock_client.query_points.return_value = SimpleNamespace(
            points=[_make_point(score=0.85)]
        )
        monkeypatch.setattr("src.services.chat.retrieval.client", lambda: mock_client)

        from src.services.chat.retrieval import multi_query_hybrid_search

        sources, metadata = await multi_query_hybrid_search(
            ["single query"],
            book_slugs=["islp"],
            top_k=5,
        )

        assert isinstance(sources, list)
        assert metadata.rewrittenQuery == "single query"

    @pytest.mark.asyncio
    async def test_empty_queries_raises(self) -> None:
        """Passing an empty list must raise ValueError."""
        from src.services.chat.retrieval import multi_query_hybrid_search

        with pytest.raises(ValueError, match="non-empty"):
            await multi_query_hybrid_search([], book_slugs=["islp"])
