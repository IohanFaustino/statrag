"""Orchestrator-workers drafting workflow (per author).

The orchestrator groups the retrieved sources by author, runs one worker LLM
per author (in parallel) to brief that author's treatment of the concept, then a
synthesizer integrates the briefs into the final ``DeepTutorAnswer`` — comparing
authors explicitly. Selected via ``ChatRequest.tutorWorkflow == "orchestrator"``.

Falls back (returns ``(None, {})``) whenever it cannot do better than the
single-draft path (fewer than 2 authors, or all workers failed), so the caller
can use ``_stream_draft`` instead.

Imports from ``deep_tutor`` are done at module load; ``deep_tutor`` imports THIS
module lazily inside ``run_deep_tutor`` to avoid a circular import.
"""
from __future__ import annotations

import asyncio
import logging

from src.core.config import settings
from src.services.chat.prompts.deep_tutor import (
    AUTHOR_WORKER_PROMPT,
    DEEP_TUTOR_INSTRUCTIONS,
    SYNTHESIZER_ADDENDUM,
    format_source_bundle,
)
from src.services.chat.retrievers.diversity import author_key
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import (
    AuthorBrief,
    DeepTutorAnswer,
    SynthesisPlan,
    WorkerTask,
)

from src.services.chat.agents.ow_harness import maybe_traced

# Low-level helpers shared with the single-draft path.
from src.services.chat.agents.deep_tutor import (
    _async_client,
    _format_figure_bundle,
    _format_plan_block,
    _stream_structured,
)

logger = logging.getLogger(__name__)


def _group_sources_by_author(sources: list[Source]) -> dict[str, list[Source]]:
    """Group sources by normalized author identity, preserving first-seen order."""
    groups: dict[str, list[Source]] = {}
    for s in sources:
        groups.setdefault(author_key(s), []).append(s)
    return groups


async def run_author_worker(
    query: str, thesis: str, author: str, srcs: list[Source], *, model: str | None = None
) -> AuthorBrief | None:
    """Brief how one author treats the concept, grounded only in *srcs*.
    Best-effort: returns ``None`` on any failure."""
    if not srcs:
        return None
    chosen_model = model or settings.openai_model_nano
    oa = _async_client(chosen_model)
    user = (
        f"<question>\n{query}\n</question>\n\n"
        f"<thesis>{thesis}</thesis>\n\n"
        f"<author>{author}</author>\n\n"
        f"{format_source_bundle(srcs)}\n\n"
        f"Return this author's brief JSON now."
    )
    try:
        resp = await oa.chat.completions.parse(
            model=chosen_model,
            messages=[
                {"role": "system", "content": AUTHOR_WORKER_PROMPT},
                {"role": "user", "content": user},
            ],
            response_format=AuthorBrief,
            temperature=0.0,
            max_completion_tokens=420,
        )
        brief = resp.choices[0].message.parsed
        if brief and not brief.author:
            brief.author = author
        return brief
    except Exception:  # noqa: BLE001
        logger.exception("author worker failed for %s", author)
        return None


def _format_author_briefs(briefs: list[AuthorBrief]) -> str:
    parts: list[str] = ["<author_briefs>"]
    for b in briefs:
        ranks = ", ".join(f"#{r}" for r in b.source_ranks) if b.source_ranks else "—"
        parts.append(f"<brief author='{b.author}' sources='{ranks}'>")
        if b.summary:
            parts.append(b.summary)
        for kp in b.key_points:
            parts.append(f"- {kp}")
        parts.append("</brief>")
    parts.append("</author_briefs>")
    return "\n".join(parts)


def _fallback_tasks(sources: list[Source]) -> list[WorkerTask]:
    """Per-author split — used when the orchestrator LLM declines/fails."""
    return [
        WorkerTask(focus=srcs[0].authors_short or author, source_ranks=[s.rank for s in srcs])
        for author, srcs in _group_sources_by_author(sources).items()
    ]


async def run_orchestrator_workers(
    query: str,
    sources: list[Source],
    plan: SynthesisPlan | None,
    *,
    orchestrator_model: str | None = None,
    worker_model: str | None = None,
    synth_model: str | None = None,
    figures: list | None = None,
    on_aspect_delta=None,
    on_briefs=None,
) -> tuple[DeepTutorAnswer | None, dict[str, str]]:
    """Orchestrator LLM (dynamic subtasks) → parallel workers → streaming
    synthesizer. Falls back to a per-author split when the orchestrator
    declines. Returns ``(None, {})`` to tell the caller to use the single
    draft (too thin to orchestrate).

    *on_briefs* — optional callable invoked with the list of worker
    ``AuthorBrief`` objects just before synthesis. Intended for
    eval/observability capture; any exception in the hook is swallowed so
    it can never break drafting."""
    # 1. Subtasks come from the Planner (Planner + Orchestrator are one agent —
    # plan.tasks). No second LLM call. Fall back to a per-author split when the
    # plan didn't decompose.
    tasks = (plan.tasks if plan else None) or _fallback_tasks(sources)

    # 2. Map each task's source ranks to Sources (bad/empty ranks → all sources).
    by_rank = {s.rank: s for s in sources}
    built: list[tuple[str, list[Source]]] = []
    for t in tasks:
        srcs = [by_rank[r] for r in t.source_ranks if r in by_rank] or sources
        built.append((t.focus or "this source set", srcs))
    if len(built) < 2:
        # One subtask only — no advantage over the single draft.
        return None, {}

    # 3. Run the workers in parallel.
    thesis = plan.thesis if plan else ""
    results = await asyncio.gather(
        *(maybe_traced(run_author_worker, name="ow.worker")(query, thesis, focus, srcs, model=worker_model)
          for focus, srcs in built),
        return_exceptions=True,
    )
    briefs = [r for r in results if isinstance(r, AuthorBrief) and (r.summary or r.key_points)]
    if len(briefs) < 2:
        logger.info("orchestrator: <2 usable worker briefs; falling back to single draft")
        return None, {}

    if on_briefs is not None:
        try:
            on_briefs(briefs)
        except Exception:  # noqa: BLE001  (a capture hook must never break drafting)
            logger.exception("on_briefs hook failed; continuing")

    # Synthesizer: same DeepTutorAnswer schema + draft rules + briefs addendum.
    plan_block = _format_plan_block(plan)
    user = (
        f"<question>\n{query}\n</question>\n\n"
        f"{format_source_bundle(sources)}\n\n"
        f"{(plan_block + chr(10) + chr(10)) if plan_block else ''}"
        f"{_format_author_briefs(briefs)}\n\n"
        f"{_format_figure_bundle(figures or [])}\n\n"
        f"Synthesize the author briefs into the answer now. Fill every field of "
        f"the DeepTutorAnswer schema, integrate into one throughline, and compare "
        f"the authors explicitly per the system prompt."
    )
    messages = [
        {"role": "system", "content": DEEP_TUTOR_INSTRUCTIONS + SYNTHESIZER_ADDENDUM},
        {"role": "user", "content": user},
    ]
    synth = synth_model or settings.openai_model_nano
    if synth.startswith("deepseek"):
        # Synthesizer needs the OpenAI structured path; nano covers deepseek picks.
        synth = settings.openai_model_nano
    return await _stream_structured(messages, synth, on_aspect_delta)
