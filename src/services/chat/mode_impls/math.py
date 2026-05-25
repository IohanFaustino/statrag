"""v2 ``math`` mode — LaTeX-heavy answer with optional vision-on-figure tool."""
from __future__ import annotations

import asyncio

from src.core.config import settings
from src.services.chat.mode_impls._common import build_structured_agent
from src.services.chat.prompts.math import INSTRUCTIONS
from src.services.chat.schemas.output import MathAnswer
from src.services.chat.tools import (
    inspect_figure_tool,
    retrieve,
    retrieve_figures,
)

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
            tools=[retrieve, retrieve_figures, inspect_figure_tool],
            response_format=MathAnswer,
            model=settings.openai_model_full,
        )
        return _AGENT


def _reset_agent_cache() -> None:
    global _AGENT
    _AGENT = None


build_agent.cache_clear = _reset_agent_cache  # type: ignore[attr-defined]
