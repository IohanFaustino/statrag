from __future__ import annotations

import pytest

from src.services.chat.schemas import HighlightRange, Source


def _make_source(rank: int, title: str, excerpt: str, chunkId: str) -> Source:
    return Source(
        rank=rank,
        book="x",
        chapter="ch01",
        section="§1",
        title=title,
        excerpt=excerpt,
        score=0.5 - rank * 0.1,
        chunkId=chunkId,
        chunk=excerpt,
        highlights=[],
    )


class _FakeModel:
    """Fake CrossEncoder whose predict returns a fixed list of scores."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def predict(self, pairs: list, show_progress_bar: bool = False) -> list[float]:
        return self._scores


def test_reranker_reorders_monotonically() -> None:
    """Cross-encoder score should override RRF rank order."""
    from src.services.chat.rerankers import CrossEncoderReranker

    r = CrossEncoderReranker()
    # inject fake model without triggering HuggingFace download
    r.__dict__["_model"] = _FakeModel([0.9, 0.1])

    src1 = _make_source(1, "rel", "bias variance", "a")
    src2 = _make_source(2, "irrel", "pizza", "b")

    out = r.rerank("bias variance", [src1, src2], top_n=2)

    assert out[0].title == "rel"
    assert out[0].rank == 1
    assert out[0].score == pytest.approx(0.9)


def test_reranker_top_n_caps_output() -> None:
    """Output length must equal top_n even when more hits are supplied."""
    from src.services.chat.rerankers import CrossEncoderReranker

    r = CrossEncoderReranker()
    scores = [0.3, 0.9, 0.1, 0.7, 0.5]
    r.__dict__["_model"] = _FakeModel(scores)

    hits = [_make_source(i + 1, f"doc{i}", f"text {i}", str(i)) for i in range(5)]
    out = r.rerank("some query", hits, top_n=3)

    assert len(out) == 3
    # Verify they are in descending score order.
    assert out[0].score >= out[1].score >= out[2].score


def test_reranker_empty_hits() -> None:
    """Empty input must return empty output without touching the model."""
    from src.services.chat.rerankers import CrossEncoderReranker

    r = CrossEncoderReranker()
    # _model is NOT set — any access would raise AttributeError via cached_property
    # (the property calls the real CrossEncoder import).  We verify it is never
    # accessed by asserting "_model" is absent from the instance __dict__.
    out = r.rerank("anything", [], top_n=5)

    assert out == []
    assert "_model" not in r.__dict__
