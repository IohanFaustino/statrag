"""v2 ``tutor`` mode — LangChain create_agent with the retrieve tool.

T13-E: tutor uses ``response_format=TutorAnswer`` so every response is a
structured JSON with per-claim citation spans, an H2-section index, and
optional LaTeX / figure references. The frontend renders inline `[¹]`
markers as clickable citation cards.

Env override ``TUTOR_FREE_TEXT=1`` rolls back to free-form text.

Builder is async + cached: the first request constructs the agent inside
the active asyncio event loop (required by the async aiosqlite-backed
checkpointer); all subsequent requests reuse the cached instance.

Chinese-wall: imports only from ``src.core.*`` and sibling
``src.services.chat.*`` modules.
"""
from __future__ import annotations

import asyncio
import os

from langchain.agents import create_agent

from src.core.config import settings
from src.services.chat.checkpointer import get_async_checkpointer
from src.services.chat.prompts.tutor import TUTOR_INSTRUCTIONS
from src.services.chat.schemas.output import TutorAnswer
from src.services.chat.tools import retrieve

_AGENT = None
_BUILD_LOCK: asyncio.Lock | None = None


def _lock() -> asyncio.Lock:
    """Return a process-wide async lock — created lazily so module import
    doesn't need a running event loop."""
    global _BUILD_LOCK
    if _BUILD_LOCK is None:
        _BUILD_LOCK = asyncio.Lock()
    return _BUILD_LOCK


async def build_agent():
    """Return the cached v2 tutor agent. Lazy + asyncio-safe.

    Must be awaited from inside an event loop because the underlying
    async checkpointer creates an aiosqlite connection.
    """
    global _AGENT
    if _AGENT is not None:
        return _AGENT
    async with _lock():
        if _AGENT is not None:
            return _AGENT
        kwargs: dict = {
            "model": f"openai:{settings.openai_model_nano}",
            "tools": [retrieve],
            "system_prompt": TUTOR_INSTRUCTIONS,
            "checkpointer": await get_async_checkpointer(),
        }
        if not os.environ.get("TUTOR_FREE_TEXT"):
            kwargs["response_format"] = TutorAnswer
        _AGENT = create_agent(**kwargs)
        return _AGENT


def _reset_agent_cache() -> None:
    """Test-only helper that drops the cached agent."""
    global _AGENT
    _AGENT = None


# Preserve the lru_cache-style API some tests use.
build_agent.cache_clear = _reset_agent_cache  # type: ignore[attr-defined]
