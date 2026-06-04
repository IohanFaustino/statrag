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
import os as _os
import re

from src.core.config import settings

SYNTHESIS_SKILL_DIR = _os.path.join(_os.path.dirname(__file__), "ow_skills")

logger = logging.getLogger(__name__)

_SYNTH_INSTRUCTIONS = (
    "You synthesize multiple authors' briefs into one tutor answer. The briefs are "
    "files under /briefs/. READ every /briefs/*.md file, then write a single coherent "
    "answer that integrates them into one throughline and COMPARES the authors "
    "explicitly (not a concatenation). Ground every claim in the briefs."
)


def _sum_usage(meta) -> tuple[int, int]:
    """Sum input/output tokens across all models in a UsageMetadataCallbackHandler."""
    if not meta:
        return (0, 0)
    it = ot = 0
    for v in meta.values():
        it += int(v.get("input_tokens", 0) or 0)
        ot += int(v.get("output_tokens", 0) or 0)
    return (it, ot)


async def _run_agent(agent, user_content: str) -> tuple[str, int, int]:
    """Invoke a deep agent, capturing total token usage (main + subagents + tool
    turns) via UsageMetadataCallbackHandler. Returns (text, in_tok, out_tok)."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": user_content}]},
        {"configurable": {"thread_id": "ow-c"}, "callbacks": [cb]})
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    text = (msgs[-1].content if msgs else "") or ""
    it, ot = _sum_usage(getattr(cb, "usage_metadata", None))
    return (text, it, ot)


def _build_store(briefs):
    """InMemoryStore preloaded with one /briefs/<author>.md per brief."""
    from deepagents.backends.utils import create_file_data
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    for b in briefs:
        store.put(namespace=("filesystem",), key=f"/briefs/{_slug(b.author)}.md",
                  value=create_file_data(_brief_md(b)))
    return store


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
    except (ImportError, TypeError) as e:  # None-in-sys.modules raises TypeError
        raise RuntimeError("pip install deepagents to run harness level 3") from e
    from langchain_openai import ChatOpenAI

    # api_key explicit: settings loads .env but does NOT export to os.environ, so
    # ChatOpenAI's env-var lookup misses it (would raise "Missing credentials").
    store = _build_store(briefs)
    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(model=model, tools=[], system_prompt=_SYNTH_INSTRUCTIONS,
                              backend=lambda rt: StoreBackend(rt), store=store)
    text, _it, _ot = await _run_agent(agent, f"Question: {query}\nSynthesize the briefs now.")
    return text


async def synthesize_with_skill(
    query: str, sources, briefs, *, model: str | None = None
) -> tuple[str, int, int]:
    """L3b: deepagents synthesizer + the written synthesis SKILL. Returns
    (text, in_tok, out_tok).

    *model* — OpenAI model id for the ChatOpenAI agent. Defaults to
    ``settings.openai_model_nano`` when ``None`` or not provided."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run harness level 3b") from e
    from langchain_openai import ChatOpenAI
    from pathlib import Path

    chosen = model or settings.openai_model_nano

    store = _build_store(briefs)
    # Preload the synthesis skill into the store's /skills/ tree.
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md",
              value=create_file_data(skill_md))

    lc_model = ChatOpenAI(model=chosen, temperature=0.0,
                          api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=lc_model, tools=[],
        system_prompt="Use the synthesis skill to synthesize the briefs in /briefs/.",
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"])
    return await _run_agent(agent, f"Question: {query}\nSynthesize the briefs now.")


async def synthesize_with_subagents(query: str, sources, briefs) -> tuple[str, int, int]:
    """L4: deepagents synthesizer that delegates each author's brief to an
    author-analyst subagent, then integrates. Returns (text, in_tok, out_tok)."""
    try:
        import deepagents  # noqa: F401
        from deepagents import create_deep_agent
        from deepagents.backends import StoreBackend
        from deepagents.backends.utils import create_file_data
    except (ImportError, TypeError) as e:
        raise RuntimeError("pip install deepagents to run harness level 4") from e
    from langchain_openai import ChatOpenAI
    from pathlib import Path

    store = _build_store(briefs)
    skill_md = (Path(SYNTHESIS_SKILL_DIR) / "synthesis" / "SKILL.md").read_text(encoding="utf-8")
    store.put(namespace=("filesystem",), key="/skills/synthesis/SKILL.md",
              value=create_file_data(skill_md))

    authors = "; ".join(_slug(b.author) for b in briefs)
    model = ChatOpenAI(model=settings.openai_model_nano, temperature=0.0,
                       api_key=settings.openai_api_key)
    agent = create_deep_agent(
        model=model, tools=[],
        system_prompt=(
            "For EACH author brief file in /briefs/, delegate to the 'author-analyst' "
            "subagent (via the task tool) to extract that author's key points from its "
            f"brief file. Author brief slugs: {authors}. Then integrate all analyses into "
            "one comparative answer that retains every key point and compares the authors."),
        subagents=[{
            "name": "author-analyst",
            "description": "Read one author's brief file and report its key points.",
            "system_prompt": "Read the named /briefs/<author>.md file and return its key points faithfully.",
            "skills": ["/skills/"],
        }],
        backend=lambda rt: StoreBackend(rt), store=store, skills=["/skills/"])
    return await _run_agent(agent, f"Question: {query}\nProduce the comparative synthesis now.")
