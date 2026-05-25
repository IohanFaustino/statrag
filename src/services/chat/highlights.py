"""Sentence-level highlight reranker for the chat service.

Computes cosine-similarity between the query and each sentence in a chunk,
returning the top-N sentence ranges as :class:`HighlightRange` objects.

Chinese-wall: imports only from ``src.core.*`` and stdlib/third-party.
"""
from __future__ import annotations

import math
import re

import openai as _openai

from src.core.config import settings
from src.services.chat.schemas import HighlightRange

# Sentence boundary pattern: split after . ! ? followed by whitespace.
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _cosine(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two equal-length float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts in a single OpenAI API call."""
    oa = _openai.OpenAI(api_key=settings.openai_api_key)
    resp = oa.embeddings.create(model=settings.embedding_model, input=texts)
    # API returns embeddings in the same order as input
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [item.embedding for item in ordered]


def _split_sentences(chunk: str) -> list[tuple[str, int, int]]:
    """Split *chunk* into (sentence, start, end) tuples using char offsets.

    Falls back to a single span covering the whole chunk if no split is found.
    """
    parts = _SENT_RE.split(chunk)
    if len(parts) <= 1:
        return [(chunk, 0, len(chunk))]

    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for i, part in enumerate(parts):
        start = cursor
        end = start + len(part)
        spans.append((part, start, end))
        # Account for the whitespace consumed by the split (1 char minimum)
        if i < len(parts) - 1:
            # Find the actual delimiter length in the original string
            cursor = end
            # Skip any whitespace after the sentence boundary
            while cursor < len(chunk) and chunk[cursor].isspace():
                cursor += 1
    return spans


def compute_highlights(
    query: str,
    chunk: str,
    *,
    max_spans: int = 3,
) -> list[HighlightRange]:
    """Compute sentence-level highlight ranges within *chunk*.

    Embeds the query and each sentence, cosine-ranks them, and returns the
    top ``max_spans`` sentences whose similarity exceeds 0.5.

    Args:
        query: The search query used to score sentences.
        chunk: Full text of the retrieved chunk.
        max_spans: Maximum number of highlight spans to return.

    Returns:
        List of :class:`HighlightRange` ordered by similarity (descending).
        Returns a single full-chunk range when there are ≤ 2 sentences.
        Returns an empty list if the chunk is empty.
    """
    if not chunk:
        return []

    sentences = _split_sentences(chunk)

    # Short-circuit: ≤ 2 sentences → return full-chunk range without extra call
    if len(sentences) <= 2:
        return [HighlightRange(start=0, end=len(chunk), reason="full chunk")]

    # Batch-embed query + all sentences in a single API round-trip
    texts = [query] + [s for s, _, _ in sentences]
    embeddings = _embed_batch(texts)
    query_emb = embeddings[0]
    sent_embs = embeddings[1:]

    # Score and sort sentences
    scored: list[tuple[float, int, int, str]] = []
    for emb, (text, start, end) in zip(sent_embs, sentences):
        score = _cosine(query_emb, emb)
        if score > 0.5:
            scored.append((score, start, end, text))

    scored.sort(key=lambda t: t[0], reverse=True)

    return [
        HighlightRange(start=start, end=end, reason=f"score={score:.2f}")
        for score, start, end, _text in scored[:max_spans]
    ]
