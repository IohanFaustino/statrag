"""Cross-encoder reranker wrapper.

T05 (diagnostic code §3) fixes:
- Pass up to ~2000 chars of chunk text to the model (not the 200-char
  ``excerpt`` prefix), so the cross-encoder actually exercises its 512-token
  capacity rather than scoring abbreviated previews.
- Preserve the pre-rerank RRF score on ``Source.raw_score`` so downstream
  consumers can distinguish retrieval-fusion confidence from cross-encoder
  logits.
- Provide an async ``arerank`` method that wraps ``predict`` in
  ``asyncio.to_thread`` so reranking does not block the event loop.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import logging
from functools import cached_property

from src.core.config import settings
from src.services.chat.schemas import Source

logger = logging.getLogger(__name__)

# Cross-encoder excerpt cap. The model max_length is 512 tokens (~1500-2000
# chars); we feed a generous 2000-char window so the model sees the chunk
# body, not just its first 200-char preview.
_RERANK_MAX_CHARS = 2000


class CrossEncoderReranker:
    """Lazy-loaded BAAI/bge-reranker-v2-m3 cross-encoder.

    Loads ~600MB on first call; cached for process lifetime.
    Memory budget: <= 2GB resident (NFR10).
    """

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or settings.reranker_model

    @cached_property
    def _model(self):
        from sentence_transformers import CrossEncoder

        logger.info("Loading reranker: %s", self.model_name)
        return CrossEncoder(self.model_name, max_length=512)

    def _build_pairs(self, query: str, hits: list[Source]) -> list[tuple[str, str]]:
        """Return ``(query, chunk)`` pairs with the chunk capped to the
        rerank window. T05: prefer the full chunk over the 200-char excerpt.
        """
        return [
            (query, (h.chunk or h.excerpt or "")[:_RERANK_MAX_CHARS])
            for h in hits
        ]

    def _apply_scores(
        self, hits: list[Source], scores, top_n: int
    ) -> list[Source]:
        """Sort by score desc, take top_n, mutate rank/score in place."""
        ranked = sorted(zip(scores, hits), key=lambda t: -float(t[0]))[:top_n]
        out: list[Source] = []
        for new_rank, (score, h) in enumerate(ranked, start=1):
            # T05: preserve the pre-rerank score so callers can read both
            # the retrieval-fusion score and the cross-encoder logit.
            if h.raw_score is None:
                h.raw_score = h.score
            h.rank = new_rank
            h.score = float(score)
            out.append(h)
        return out

    def rerank(self, query: str, hits: list[Source], top_n: int) -> list[Source]:
        """Rerank *hits* by cross-encoder score and return the top *top_n*.

        Sync entry point. Blocks the caller. Use :meth:`arerank` from async
        contexts to avoid stalling the event loop.

        Args:
            query: The user query string.
            hits: Candidate sources from RRF retrieval.
            top_n: Maximum number of sources to return after reranking.

        Returns:
            Reranked list of sources with updated rank and score fields and
            the pre-rerank score preserved on ``raw_score``.
        """
        if not hits:
            return hits
        pairs = self._build_pairs(query, hits)
        scores = self._model.predict(pairs, show_progress_bar=False)
        return self._apply_scores(hits, scores, top_n)

    async def arerank(
        self, query: str, hits: list[Source], top_n: int
    ) -> list[Source]:
        """Async wrapper that runs the model in a worker thread.

        T05: prevents the cross-encoder's CPU-heavy ``predict`` call from
        blocking the event loop when the reranker is invoked from an async
        pipeline.
        """
        if not hits:
            return hits
        pairs = self._build_pairs(query, hits)

        def _predict():
            return self._model.predict(pairs, show_progress_bar=False)

        scores = await asyncio.to_thread(_predict)
        return self._apply_scores(hits, scores, top_n)


_REGISTRY: CrossEncoderReranker | None = None


def get_reranker() -> CrossEncoderReranker:
    """Return the process-level singleton reranker, creating it on first call."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CrossEncoderReranker()
    return _REGISTRY
