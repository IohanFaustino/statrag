"""Shared helpers for v2 single-agent mode builders.

All single-agent modes share the same shape:

- one ``create_agent`` call with a fixed tool set and (optional)
  ``response_format`` Pydantic schema,
- the shared ``AsyncSqliteSaver`` checkpointer keyed by ``thread_id``,
- a process-cached factory so the heavy LangGraph compile happens once.

Builders are async because the underlying async checkpointer must
``await aiosqlite.connect(...)`` to bind a real Connection — not a
coroutine — to the saver instance.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

from typing import Iterable

from langchain.agents import create_agent

from src.core.config import settings
from src.services.chat.checkpointer import get_async_checkpointer


async def build_structured_agent(
    *,
    system_prompt: str,
    tools: Iterable,
    response_format: type | None,
    model: str | None = None,
):
    """Compile a single-agent v2 mode agent with shared infra.

    MUST be awaited from inside an active asyncio event loop because the
    underlying async checkpointer creates an aiosqlite connection.

    Args:
        system_prompt: System message (mode INSTRUCTIONS constant).
        tools: Iterable of ``@tool``-decorated functions.
        response_format: Optional Pydantic schema class for native
            constrained decoding (T06/ADR-008).
        model: Optional model id; defaults to the nano model from settings.

    Returns:
        A compiled LangGraph agent ready for ``invoke``/``astream``.
    """
    model_id = model or settings.openai_model_nano
    kwargs: dict = {
        "model": f"openai:{model_id}",
        "tools": list(tools),
        "system_prompt": system_prompt,
        "checkpointer": await get_async_checkpointer(),
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    return create_agent(**kwargs)
