"""Evaluation metrics for the RAG chat service.

All LLM-judge metrics are async. Deterministic metrics (precision/recall) are
synchronous.

Wall rule: imports only src.core.*. Does NOT import src.services.chat.
"""
from __future__ import annotations

import json

import openai as _openai

from src.core.config import settings


async def _judge(prompt: str, *, max_tokens: int = 300) -> dict:
    """Call the nano model as an LLM judge and parse its JSON response.

    Args:
        prompt: The evaluation prompt to send.
        max_tokens: Maximum tokens for the judge response.

    Returns:
        Parsed JSON dict, or empty dict on parse failure.
    """
    client = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    raw = resp.choices[0].message.content or "{}"
    # Strip markdown code fences if the model wraps its JSON
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def context_precision(retrieved_chunks: list[dict], gold_chunk_id: str | None) -> float:
    """Fraction of retrieved chunks whose ``chunkId`` matches gold.

    Args:
        retrieved_chunks: List of chunk dicts from the chat response (each
            expected to carry a ``chunkId`` key).
        gold_chunk_id: The authoritative chunk identifier, or None when there
            is no gold reference.

    Returns:
        Precision score in [0, 1]. Returns 1.0 when ``gold_chunk_id`` is None
        (nothing to compare — permissive default).
    """
    if not retrieved_chunks:
        return 0.0
    if not gold_chunk_id:
        return 1.0  # nothing to compare; permissive
    hits = sum(1 for c in retrieved_chunks if c.get("chunkId") == gold_chunk_id)
    return hits / len(retrieved_chunks)


def context_recall(retrieved_chunks: list[dict], gold_chunk_id: str | None) -> float:
    """1 if gold chunk is anywhere in the retrieved set, else 0.

    Args:
        retrieved_chunks: List of chunk dicts from the chat response.
        gold_chunk_id: The authoritative chunk identifier, or None.

    Returns:
        1.0 if the gold chunk is found (or gold is absent), otherwise 0.0.
    """
    if not gold_chunk_id:
        return 1.0
    return 1.0 if any(c.get("chunkId") == gold_chunk_id for c in retrieved_chunks) else 0.0


async def faithfulness(answer: str, contexts: list[str]) -> float:
    """LLM-judge: fraction of claims in answer supported by contexts.

    Args:
        answer: The model-generated answer text.
        contexts: List of retrieved chunk texts used to produce the answer.

    Returns:
        Faithfulness score in [0, 1].  1.0 means all claims are grounded.
    """
    prompt = (
        "Given an ANSWER and a list of CONTEXTS, count how many distinct factual "
        "claims in ANSWER are NOT directly supported by any CONTEXT. "
        "Return ONLY JSON: {\"total_claims\": int, \"unsupported\": int}.\n\n"
        f"ANSWER:\n{answer}\n\n"
        f"CONTEXTS:\n{chr(10).join(contexts[:5])}"
    )
    j = await _judge(prompt)
    total = max(int(j.get("total_claims", 0)), 1)
    return 1.0 - (int(j.get("unsupported", 0)) / total)


async def answer_relevance(answer: str, question: str) -> float:
    """LLM-judge: 0..1 score for how well answer addresses the question.

    Args:
        answer: The model-generated answer text.
        question: The original user question.

    Returns:
        Relevance score clamped to [0, 1].
    """
    prompt = (
        "Rate from 0.0 to 1.0 how well the ANSWER addresses the QUESTION. "
        "Return ONLY JSON: {\"score\": float}.\n\n"
        f"QUESTION: {question}\n\nANSWER: {answer}"
    )
    j = await _judge(prompt)
    s = float(j.get("score", 0.0))
    return max(0.0, min(1.0, s))
