"""v2 ``compare`` mode — uses retrieve_per_book to balance cross-book coverage.

T10 (ADR-006). Replaces v1 single-shot RRF that let one book dominate.

Async builder — see `mode_impls._common` docstring for the rationale.
"""
from __future__ import annotations

import asyncio

from src.core.config import settings
from src.services.chat.mode_impls._common import build_structured_agent
from src.services.chat.prompts.compare import INSTRUCTIONS
from src.services.chat.schemas.output import CompareAnswer
from src.services.chat.tools import retrieve, retrieve_per_book

_AGENT = None
_LOCK: asyncio.Lock | None = None


def _lock() -> asyncio.Lock:
    global _LOCK
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    return _LOCK


async def build_agent():
    global _AGENT
    if _AGENT is not None:
        return _AGENT
    async with _lock():
        if _AGENT is not None:
            return _AGENT
        _AGENT = await build_structured_agent(
            system_prompt=INSTRUCTIONS,
            tools=[retrieve, retrieve_per_book],
            response_format=CompareAnswer,
            model=settings.openai_model_full,
        )
        return _AGENT


def _reset_agent_cache() -> None:
    global _AGENT
    _AGENT = None


build_agent.cache_clear = _reset_agent_cache  # type: ignore[attr-defined]
