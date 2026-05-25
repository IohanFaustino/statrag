"""Query rewriter — turns a multi-turn message into a standalone retrieval query.

T03 (B2 fix): replaces the v1 concat-hack with a real LLM rewrite step.
The LLM is asked to:
- expand acronyms,
- resolve pronouns from prior turns,
- drop conversational filler,
- produce a single, retrieval-friendly question.

Falls back to the original query when:
- there is no prior history (nothing to resolve),
- the LLM call fails or returns empty,
- the env var ``REWRITER_MODE=concat`` is set (legacy rollback).

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import openai as _openai

from src.core.config import settings

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = (
    "You rewrite the user's latest message into a single standalone retrieval "
    "query. Expand acronyms (e.g. OLS -> Ordinary Least Squares), resolve "
    "pronouns from the prior turns, drop conversational filler. Reply with "
    "ONLY the rewritten query — no quotes, no explanation, one line."
)


def _history_user_turns(history: list[dict] | None, n: int = 3) -> list[str]:
    """Return the last *n* user turns from *history* as plain strings."""
    if not history:
        return []
    out: list[str] = []
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            joined = " ".join(filter(None, text_parts))
            if joined:
                out.append(joined)
        if len(out) >= n:
            break
    return list(reversed(out))


def _concat_fallback(query: str, history: list[dict] | None) -> str:
    """v1 behaviour preserved for ``REWRITER_MODE=concat`` rollback."""
    user_turns = _history_user_turns(history, n=2)
    if not user_turns:
        return query
    return " | ".join([*user_turns, query])


@lru_cache(maxsize=256)
def _cached_rewrite(history_key: str, query: str) -> str:
    """Synchronous cache key. The actual LLM call happens in :func:`arewrite_query`."""
    # Placeholder; arewrite_query maintains its own cache via this key
    return ""


async def arewrite_query(query: str, history: list[dict] | None = None) -> str:
    """Return a retrieval-optimised standalone version of *query*.

    Args:
        query: The user's latest message.
        history: Optional list of `{role, content}` dicts ordered oldest-first.

    Returns:
        The rewritten query, or *query* unchanged when no history exists
        / the LLM fails / legacy mode is on.
    """
    if os.environ.get("REWRITER_MODE") == "concat":
        return _concat_fallback(query, history)

    user_turns = _history_user_turns(history, n=3)
    if not user_turns:
        return query

    history_block = "\n".join(f"- {t}" for t in user_turns)
    prompt = (
        f"Prior user turns:\n{history_block}\n\n"
        f"Latest message: {query}\n\n"
        "Rewritten standalone query:"
    )

    try:
        oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
            temperature=0.0,
        )
        out = (resp.choices[0].message.content or "").strip()
        if out and out.lower() != query.strip().lower():
            return out
    except Exception:  # noqa: BLE001
        logger.exception("rewriter: LLM call failed, falling back to raw query")

    return query


def rewrite_query(query: str, history: list[dict] | None = None) -> str:
    """Synchronous shim around :func:`arewrite_query` for v1 callers.

    Runs the coroutine in a fresh asyncio loop. Avoids nested-loop hazards
    when invoked from an existing event loop by detecting that case and
    falling back to the cheap concat heuristic.

    Args:
        query: Same as :func:`arewrite_query`.
        history: Same.

    Returns:
        Same.
    """
    import asyncio

    if not history:
        return query

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop — cannot block on the coroutine
            # without risking deadlock. Fall back to the cheap concat heuristic;
            # async callers should invoke :func:`arewrite_query` directly.
            return _concat_fallback(query, history)
    except RuntimeError:
        pass

    return asyncio.run(arewrite_query(query, history))
