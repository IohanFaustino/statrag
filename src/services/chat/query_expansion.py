"""Async LLM-driven query expansion strategies for the chat service.

Three strategies: HyDE, multi-query paraphrase, and decomposition.
All use a lightweight one-shot OpenAI completion (non-streaming).

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``
modules.
"""
from __future__ import annotations

import json
import logging

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences

logger = logging.getLogger(__name__)


async def _llm_short(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 300,
) -> str:
    """One-shot async OpenAI completion. Returns raw text.

    Args:
        prompt: The user prompt to send.
        model: Override model; defaults to ``settings.openai_model_nano``.
        max_tokens: Cap on generated tokens.

    Returns:
        Raw text content of the first choice.
    """
    client = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=model or settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


async def hyde(query: str, *, model: str | None = None) -> str:
    """Hypothetical Document Embedding: generate a 3-sentence textbook-style answer.

    Generates a short hypothetical passage from a statistics/econometrics textbook
    that would directly answer *query*. The passage is then used as an additional
    dense-retrieval query alongside the original.

    Args:
        query: The user query string.
        model: Optional model override; defaults to ``settings.openai_model_nano``.

    Returns:
        A 3-sentence hypothetical textbook excerpt (stripped).
    """
    p = (
        "Write a 3-sentence hypothetical excerpt from a statistics/econometrics textbook "
        "that would directly answer the following query. Use precise mathematical "
        "language. Do NOT include preamble or meta-commentary.\n\n"
        f"Query: {query}"
    )
    return (await _llm_short(p, model=model, max_tokens=250)).strip()


async def multi_query(
    query: str,
    *,
    n: int = 3,
    model: str | None = None,
) -> list[str]:
    """Generate *n* alternative phrasings of *query*.

    Prompts the LLM to return a JSON array of short alternative query strings
    using diverse vocabulary (formal stats, applied econometrics, ML terms).

    Args:
        query: Original query string.
        n: Number of paraphrases requested.  Returns ``[]`` when ``n <= 0``.
        model: Optional model override; defaults to ``settings.openai_model_nano``.

    Returns:
        List of alternative query strings (up to *n*).  Empty on JSON-parse
        failure.
    """
    if n <= 0:
        return []
    p = (
        f"Generate {n} alternative short phrasings of this query for retrieval. "
        "Use diverse vocabulary (formal stats, applied econometrics, ML terms). "
        "Return ONLY a JSON array of strings, no other text.\n\n"
        f"Query: {query}"
    )
    raw = await _llm_short(p, model=model, max_tokens=200)
    try:
        arr = json.loads(strip_fences(raw))
        if isinstance(arr, list):
            return [str(s) for s in arr[:n]]
    except Exception:  # noqa: BLE001
        logger.warning("multi_query: JSON parse failed; raw=%r", raw[:200])
    return []


async def decompose(
    query: str,
    *,
    model: str | None = None,
) -> list[str]:
    """Decompose a complex question into 2-4 atomic sub-questions.

    Each sub-question is individually answerable from a single textbook
    section.  Returns a JSON array from the LLM.

    Args:
        query: Complex question to decompose.
        model: Optional model override; defaults to ``settings.openai_model_nano``.

    Returns:
        List of atomic sub-questions.  Empty on JSON-parse failure.
    """
    p = (
        "Decompose the following question into 2-4 atomic sub-questions that are "
        "each individually answerable. Return ONLY a JSON array of strings.\n\n"
        f"Question: {query}"
    )
    raw = await _llm_short(p, model=model, max_tokens=300)
    try:
        arr = json.loads(strip_fences(raw))
        if isinstance(arr, list):
            return [str(s) for s in arr]
    except Exception:  # noqa: BLE001
        logger.warning("decompose: JSON parse failed; raw=%r", raw[:200])
    return []


async def expand_queries(query: str, *, flags: object) -> list[str]:
    """Apply ``RetrievalFlags`` to produce the final list of queries to retrieve over.

    Always includes the original query first.  Adds:

    - ``flags.hyde`` → +1 HyDE expansion.
    - ``flags.multi_query > 0`` → +N paraphrases.
    - ``flags.decompose`` → +N sub-questions.

    Order: ``[original, hyde, *multi_query, *decompose]``.  Duplicates are
    removed (case-insensitive, order-preserving).

    Args:
        query: Original user query.
        flags: A ``RetrievalFlags`` dataclass instance (or any object with the
            same attribute names).

    Returns:
        Deduplicated list of query strings, original always first.
    """
    queries: list[str] = [query]

    if getattr(flags, "hyde", False):
        try:
            h = await hyde(query)
            if h:
                queries.append(h)
        except Exception:  # noqa: BLE001
            logger.exception("hyde failed")

    n_mq = getattr(flags, "multi_query", 0)
    if n_mq:
        try:
            queries.extend(await multi_query(query, n=n_mq))
        except Exception:  # noqa: BLE001
            logger.exception("multi_query failed")

    if getattr(flags, "decompose", False):
        try:
            queries.extend(await decompose(query))
        except Exception:  # noqa: BLE001
            logger.exception("decompose failed")

    # Dedup preserving order, case-insensitive
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        k = q.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(q)
    return out
