"""v2 ``navigate`` mode — ranked location list with structured output."""
from __future__ import annotations

import asyncio

from src.services.chat.mode_impls._common import build_structured_agent
from src.services.chat.prompts.navigate import INSTRUCTIONS
from src.services.chat.schemas.output import NavigationList
from src.services.chat.tools import retrieve

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
            tools=[retrieve],
            response_format=NavigationList,
        )
        return _AGENT


def _reset_agent_cache() -> None:
    global _AGENT
    _AGENT = None


build_agent.cache_clear = _reset_agent_cache  # type: ignore[attr-defined]
