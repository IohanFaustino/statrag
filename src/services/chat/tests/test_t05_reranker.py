"""T05 acceptance: reranker uses full chunk + preserves raw_score + async wrapper."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.services.chat import rerankers
from src.services.chat.schemas import Source


def _src(rank: int, chunk_text: str, score: float = 0.5) -> Source:
    return Source(
        rank=rank,
        book="islp",
        chapter="ch1",
        section="1.1",
        title="t",
        excerpt=chunk_text[:200],
        score=score,
        chunkId=f"c-{rank}",
        chunk=chunk_text,
        highlights=[],
    )


# ---------------------------------------------------------------------------
# Pair-building: T05 — must use chunk, not excerpt
# ---------------------------------------------------------------------------


def test_build_pairs_uses_full_chunk_not_excerpt():
    rr = rerankers.CrossEncoderReranker()
    long_text = "X" * 1800
    hit = _src(rank=1, chunk_text=long_text)
    pairs = rr._build_pairs("q", [hit])
    assert len(pairs) == 1
    q, doc = pairs[0]
    assert q == "q"
    # T05 fix: model must see the full chunk window, not the 200-char excerpt
    assert len(doc) == 1800
    assert doc.startswith("X" * 100)


def test_build_pairs_caps_at_2000_chars():
    rr = rerankers.CrossEncoderReranker()
    huge = "Y" * 5000
    hit = _src(rank=1, chunk_text=huge)
    pairs = rr._build_pairs("q", [hit])
    _, doc = pairs[0]
    assert len(doc) == 2000


def test_build_pairs_falls_back_to_excerpt_when_no_chunk():
    rr = rerankers.CrossEncoderReranker()
    hit = Source(
        rank=1, book="islp", chapter="ch1", section="1.1", title="t",
        excerpt="just excerpt", score=0.5, chunkId="c", chunk="", highlights=[],
    )
    pairs = rr._build_pairs("q", [hit])
    _, doc = pairs[0]
    assert doc == "just excerpt"


# ---------------------------------------------------------------------------
# Score handling: T05 — raw_score preserved on first rerank pass
# ---------------------------------------------------------------------------


def test_apply_scores_preserves_raw_score():
    rr = rerankers.CrossEncoderReranker()
    a = _src(rank=1, chunk_text="A", score=0.42)
    b = _src(rank=2, chunk_text="B", score=0.31)
    out = rr._apply_scores([a, b], [0.9, 0.1], top_n=2)
    # a has higher cross-encoder score → comes first
    assert out[0].chunkId == "c-1"
    # raw_score holds the original RRF score
    assert out[0].raw_score == pytest.approx(0.42)
    assert out[1].raw_score == pytest.approx(0.31)
    # score is now the cross-encoder logit
    assert out[0].score == pytest.approx(0.9)


def test_apply_scores_does_not_overwrite_existing_raw_score():
    rr = rerankers.CrossEncoderReranker()
    a = _src(rank=1, chunk_text="A", score=0.42)
    a.raw_score = 0.99  # pretend a prior pass already populated it
    out = rr._apply_scores([a], [0.5], top_n=1)
    assert out[0].raw_score == 0.99  # preserved, not overwritten


def test_apply_scores_takes_top_n():
    rr = rerankers.CrossEncoderReranker()
    hits = [_src(rank=i, chunk_text=f"t-{i}", score=0.5) for i in range(1, 5)]
    out = rr._apply_scores(hits, [0.1, 0.9, 0.5, 0.7], top_n=2)
    # Ordered by score desc, taking top 2 → idx 1 (0.9), idx 3 (0.7)
    assert [h.chunkId for h in out] == ["c-2", "c-4"]
    assert [h.rank for h in out] == [1, 2]


# ---------------------------------------------------------------------------
# Empty input short-circuits in both sync + async paths
# ---------------------------------------------------------------------------


def test_rerank_empty_returns_empty():
    out = rerankers.CrossEncoderReranker().rerank("q", [], top_n=5)
    assert out == []


def test_arerank_empty_returns_empty():
    out = asyncio.run(rerankers.CrossEncoderReranker().arerank("q", [], top_n=5))
    assert out == []


# ---------------------------------------------------------------------------
# arerank: predict runs in a thread (doesn't block loop)
# ---------------------------------------------------------------------------


def test_arerank_uses_to_thread(monkeypatch):
    """T05: arerank must dispatch the CPU-heavy predict via asyncio.to_thread."""
    rr = rerankers.CrossEncoderReranker()
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.7, 0.2]
    monkeypatch.setattr(
        rerankers.CrossEncoderReranker, "_model",
        property(lambda self: fake_model),
        raising=False,
    )

    to_thread_called = {"n": 0}
    real_to_thread = asyncio.to_thread

    async def _spy(fn, *a, **kw):
        to_thread_called["n"] += 1
        return await real_to_thread(fn, *a, **kw)

    monkeypatch.setattr(asyncio, "to_thread", _spy)

    hits = [_src(rank=1, chunk_text="A"), _src(rank=2, chunk_text="B")]
    out = asyncio.run(rr.arerank("q", hits, top_n=2))
    assert to_thread_called["n"] == 1
    assert out[0].chunkId == "c-1"  # higher score
    assert out[0].score == pytest.approx(0.7)
