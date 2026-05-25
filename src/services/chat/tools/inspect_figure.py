"""Vision tool: call gpt-4o with an image URL to extract or interpret the figure.

Provides two public entry points:

- :func:`inspect_figure` — the original async helper that accepts a
  :class:`~src.services.chat.schemas.Figure` object. Used directly by the
  legacy ``orchestrator`` vision-mode branch.
- :func:`inspect_figure_tool` — an `@tool`-decorated wrapper accepting only
  JSON-serialisable args. Registered on the v2 figures/math agents so the
  LLM can call vision on demand.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import logging
import time

import openai as _openai
from langchain_core.tools import tool

from src.core.config import settings
from src.services.chat.cost import log_call
from src.services.chat.schemas import Figure

logger = logging.getLogger(__name__)


async def inspect_figure(figure: Figure, *, query: str) -> str:
    """Call gpt-4o vision on a figure URL and return a short interpretation.

    Skips the remote call when the figure has no URL (local-only or built-in
    chart kind) and returns an empty string.

    Args:
        figure: The :class:`~src.services.chat.schemas.Figure` to inspect.
        query: The user's original question, used to focus the vision prompt.

    Returns:
        A 2-3 sentence visual interpretation, or an empty string on failure
        or when no valid URL is available.
    """
    if not figure.chart or not figure.chart.startswith("http"):
        # Local-only or built-in chart kind — skip remote call.
        return ""

    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    t0 = time.monotonic()
    try:
        resp = await oa.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"This figure is from {figure.book} {figure.chapter}. "
                                f"Caption: {figure.caption}\n\n"
                                f"Question: {query}\n\n"
                                "In 2-3 sentences, describe what this figure shows and "
                                "how it relates to the question. Be specific about axes, "
                                "curves, or labels."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": figure.chart},
                        },
                    ],
                }
            ],
            max_tokens=300,
            temperature=0.0,
        )
        out: str = resp.choices[0].message.content or ""
        usage = resp.usage
        latency_ms = int((time.monotonic() - t0) * 1000)
        log_call(
            model="gpt-4o-vision",
            purpose="inspect_figure",
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            images=1,
            latency_ms=latency_ms,
            extra={"figure_ref": figure.ref, "query_len": len(query)},
        )
        return out
    except Exception:
        logger.exception("inspect_figure failed for %s", figure.ref)
        return ""


@tool
def inspect_figure_tool(
    figure_ref: str,
    chart_url: str,
    caption: str,
    query: str,
    book: str = "",
    chapter: str = "",
) -> str:
    """Ask a vision model what a specific figure shows.

    Use this after :func:`retrieve_figures` returned a candidate. Pass the
    figure's URL and caption together with the user's question to focus the
    vision model. Returns a 2-3 sentence interpretation, or an empty string
    if the URL is missing or the vision call fails.

    Args:
        figure_ref: Figure reference id (used for logging only).
        chart_url: Public HTTPS URL of the figure image.
        caption: The figure caption text.
        query: The user's question — used to focus the vision prompt.
        book: Optional book slug for log context.
        chapter: Optional chapter id for log context.

    Returns:
        A 2-3 sentence visual interpretation, or an empty string.
    """
    import asyncio

    fig = Figure(
        ref=figure_ref,
        book=book,
        chapter=chapter,
        caption=caption,
        chart=chart_url,
    )
    return asyncio.run(inspect_figure(fig, query=query))
