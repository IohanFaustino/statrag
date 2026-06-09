"""Extension-mode runner: deterministic shell + capped round loop over the
deepagents core. Emits v1 SSE event dicts.

Chinese-wall: src.core.* + sibling extension_agents + shared chat infra only."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

from src.services.chat.agents.extension_agents.agent import build_extension_agent
from src.services.chat.agents.extension_agents.scope import (
    aresolve_scope_or_clarify,
    build_structure_files,
)
from src.services.chat._fences import strip_fences
from src.services.chat.books import parse_catalog
from src.services.chat.retrieval import fetch_chapter_sections
from src.services.chat.schemas import ChatRequest, ExtensionDigest


def _max_rounds(req: ChatRequest) -> int:
    if req.extensionMaxRounds:
        return int(req.extensionMaxRounds)
    try:
        return max(1, int(os.environ.get("EXTENSION_MAX_ROUNDS", "3")))
    except ValueError:
        return 3


def _all_slugs(catalog) -> list[str]:
    return [b.slug for b in catalog]


def _section_to_dict(s) -> dict:
    if isinstance(s, dict):
        return s
    return {
        "section_id": getattr(s, "section", "") or "",
        "h2_path": getattr(s, "title", "") or getattr(s, "section", "") or "",
        "text": getattr(s, "chunk", "") or getattr(s, "excerpt", "") or "",
    }


def _filter_subtopics(sections: list[dict], subtopics: list[str]) -> list[dict]:
    if not subtopics:
        return sections
    needles = [t.lower() for t in subtopics if t]
    kept = [s for s in sections
            if any(n in (str(s.get("h2_path", "")) + " " + str(s.get("section_id", ""))).lower()
                   for n in needles)]
    return kept or sections  # fall back to whole chapter if nothing matched


async def _run_round(agent, instruction: str, thread_id: str):
    """Invoke the deep-agent for one round. Returns
    (final_text, unfilled_queries, in_tok, out_tok)."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": instruction}]},
        {"configurable": {"thread_id": thread_id}, "callbacks": [cb]},
    )
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    text = (msgs[-1].content if msgs else "") or ""
    unfilled = _parse_unfilled(result)
    it = ot = 0
    for v in (getattr(cb, "usage_metadata", None) or {}).values():
        it += int(v.get("input_tokens", 0) or 0)
        ot += int(v.get("output_tokens", 0) or 0)
    return text, unfilled, it, ot


def _parse_unfilled(result) -> list[str]:
    files = result.get("files", {}) if isinstance(result, dict) else {}
    unfilled: list[str] = []
    for path, content in files.items():
        if "/footnotes/" not in path:
            continue
        body = content if isinstance(content, str) else getattr(content, "content", "") or ""
        for line in body.splitlines():
            if line.startswith("# COVERAGE:") and "= unfilled" in line:
                q = line.split("# COVERAGE:", 1)[1].split("=", 1)[0].strip()
                if q:
                    unfilled.append(q)
    return unfilled


def _parse_digest(text: str, *, book: str, chapter: str) -> ExtensionDigest:
    raw = strip_fences(text)
    try:
        data = json.loads(raw)
        return ExtensionDigest(**data)
    except Exception:  # noqa: BLE001
        return ExtensionDigest(book=book, chapter=chapter, points=[],
                               unfilled_gaps=["could not parse agent output"])


async def run_extension(req: ChatRequest) -> AsyncIterator[dict]:
    t0 = time.time()
    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}
    catalog = parse_catalog()
    selected = [] if req.bookFilter == "ALL" else list(req.bookFilter)
    clar, res = await aresolve_scope_or_clarify(req.message, catalog=catalog,
                                                selected_slugs=selected)
    if clar is not None:
        yield clar
        yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
               "inputTokens": 0, "outputTokens": 0}
        yield {"type": "done"}
        return

    book = res.book_slug
    chapter = res.chapter_id
    yield {"type": "stage", "stage": "fetch", "label": f"Fetch {book} {chapter}"}
    raw_sections = fetch_chapter_sections(book_slug=book, chapter_id=chapter)
    sections = [_section_to_dict(s) for s in raw_sections]
    sections = _filter_subtopics(sections, res.requested_subtopics)
    structure = build_structure_files(sections)

    agent = build_extension_agent(stage_models=req.extensionModels,
                                  exclude_book=book, all_slugs=_all_slugs(catalog))
    thread_id = f"ext-{book}-{chapter}-{int(t0)}"

    seed = "\n".join(f"- {p}" for p in structure.keys())
    in_tok = out_tok = 0
    text = ""
    rounds = _max_rounds(req)
    for r in range(rounds):
        if r == 0:
            instr = (
                "These /structure files hold the chapter sections (seed them as "
                f"files first):\n{seed}\n\nFile contents follow:\n" +
                "\n\n".join(f"=== {p} ===\n{c}" for p, c in structure.items()) +
                "\n\nRun the full pipeline: analyst per section -> polish -> "
                "plan queries -> augmentor. Then emit the ExtensionDigest JSON."
            )
        else:
            instr = ("Some gap queries are still unfilled. Re-run the augmentor "
                     "ONLY for unfilled queries, then re-emit the ExtensionDigest JSON.")
        yield {"type": "stage", "stage": "augment", "label": f"Augment · round {r + 1}"}
        text, unfilled, it, ot = await _run_round(agent, instr, thread_id)
        in_tok += it
        out_tok += ot
        if not unfilled:
            break

    digest = _parse_digest(text, book=book, chapter=chapter)

    for pt in digest.points:
        yield {"type": "stage", "stage": "point", "label": pt.title}
    yield {"type": "structured_output", "schema": "ExtensionDigest", "data": digest.model_dump()}
    yield {"type": "sources_full", "sources": []}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "inputTokens": in_tok, "outputTokens": out_tok}
    yield {"type": "done"}
