# src/services/chat/agents/ow_deepagents.py
"""Harness level 3: a deepagents synthesizer agent (eval experiment).

Our nano workers still produce AuthorBriefs; here each brief is preloaded as a file
into a deepagents agent's virtual filesystem, and the agent reads the brief files and
writes the synthesis. Returns free text (no DeepTutorAnswer schema — judged as text by
the eval). deepagents is NOT a prod dependency; install it manually to run level 3.

See `deep-agents-core` / `deep-agents-memory` skills for the backend/preload API.
"""
from __future__ import annotations

import asyncio
import logging
import re

from src.core.config import settings

logger = logging.getLogger(__name__)

_SYNTH_INSTRUCTIONS = (
    "You synthesize multiple authors' briefs into one tutor answer. The briefs are "
    "files under /briefs/. READ every /briefs/*.md file, then write a single coherent "
    "answer that integrates them into one throughline and COMPARES the authors "
    "explicitly (not a concatenation). Ground every claim in the briefs."
)


def _slug(author: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (author or "author").lower()).strip("-") or "author"


def _brief_md(b) -> str:
    kps = "\n".join(f"- {k}" for k in b.key_points)
    return f"# {b.author}\n\n{b.summary}\n\n{kps}\n"


async def synthesize_with_deepagents(query: str, sources, briefs) -> str:
    """Run the deepagents synthesizer over preloaded brief files. Returns the answer
    text. Raises RuntimeError if deepagents is not installed."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
        from langgraph.store.memory import InMemoryStore
    except (ImportError, TypeError) as e:  # None-in-sys.modules raises TypeError
        raise RuntimeError("pip install deepagents to run harness level 3") from e
    from langchain_openai import ChatOpenAI

    store = InMemoryStore()
    for b in briefs:
        store.put(namespace=("filesystem",),
                  key=f"/briefs/{_slug(b.author)}.md",
                  value=create_file_data(_brief_md(b)))

    # api_key explicit: settings loads .env but does NOT export to os.environ, so
    # ChatOpenAI's env-var lookup misses it (would raise "Missing credentials").
    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=model, tools=[], system_prompt=_SYNTH_INSTRUCTIONS,
        backend=lambda rt: StoreBackend(rt), store=store)
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user",
                       "content": f"Question: {query}\nSynthesize the briefs now."}]},
        {"configurable": {"thread_id": "ow-l3"}})
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    return (msgs[-1].content if msgs else "") or ""
