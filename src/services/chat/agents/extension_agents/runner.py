"""Extension-mode runner: deterministic shell + capped round loop over the
deepagents core. Emits v1 SSE event dicts.

Chinese-wall: src.core.* + sibling extension_agents + shared chat infra only."""
from __future__ import annotations

import asyncio
import json
import os
import re as _re
import time
from typing import AsyncIterator

from src.services.chat.agents.extension_agents.agent import build_extension_agent
from src.services.chat.agents.extension_agents.scope import (
    aresolve_scope_or_clarify,
    build_structure_files,
)
from src.services.chat._fences import strip_fences
from src.services.chat.agents.extension_agents.prompts import JUDGE_PROMPT
from src.services.chat.books import parse_catalog
from src.services.chat.retrieval import fetch_chapter_sections
from src.services.chat.schemas import ChatRequest, ExtensionDigest


_AUG_LEAK = _re.compile(r"https?://|\[source\]|en\.wikipedia\.org", _re.IGNORECASE)


def curated_text_is_clean(point) -> bool:
    """Invariant guard: curated_text must carry no augmentation artefacts
    (URLs / source tags). All augmentation belongs in footnotes."""
    return _AUG_LEAK.search(point.curated_text or "") is None


def _isolate_midline_display(text: str) -> str:
    """KaTeX renders ``$$..$$`` as display math only when it OWNS its line; a
    mid-line ``$$`` leaks raw LaTeX. Convert mid-line ``$$`` to inline ``$`` so
    KaTeX renders it. A line that is wholly a ``$$..$$`` block is left intact.
    (Isolated copy — cannot import the tutor helper across the Chinese wall;
    see invariant on mid-line display math.)"""
    if not text or "$$" not in text:
        return text
    out_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        owns_line = (stripped.startswith("$$") and stripped.endswith("$$")
                     and stripped.count("$$") == 2 and len(stripped) > 4)
        out_lines.append(line if owns_line else line.replace("$$", "$"))
    return "\n".join(out_lines)


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
    (structured_response, final_text, unfilled_queries, in_tok, out_tok).

    structured_response is the schema-enforced ExtensionDigest (deepagents
    response_format=ToolStrategy(ExtensionDigest)); text is the fallback when it
    is absent."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": instruction}]},
        {"configurable": {"thread_id": thread_id}, "callbacks": [cb]},
    )
    structured = result.get("structured_response") if isinstance(result, dict) else None
    msgs = result.get("messages", []) if isinstance(result, dict) else []
    text = (msgs[-1].content if msgs else "") or ""
    unfilled = _parse_unfilled(result)
    it = ot = 0
    for v in (getattr(cb, "usage_metadata", None) or {}).values():
        it += int(v.get("input_tokens", 0) or 0)
        ot += int(v.get("output_tokens", 0) or 0)
    return structured, text, unfilled, it, ot


def _coerce_digest(structured, *, book: str, chapter: str) -> ExtensionDigest | None:
    """Turn a deepagents structured_response (ExtensionDigest instance or dict)
    into an ExtensionDigest, backfilling book/chapter if the model omitted them."""
    if structured is None:
        return None
    try:
        d = structured if isinstance(structured, ExtensionDigest) else ExtensionDigest(
            **(structured if isinstance(structured, dict) else structured.model_dump())
        )
    except Exception:  # noqa: BLE001
        return None
    if not d.book:
        d.book = book
    if not d.chapter:
        d.chapter = chapter
    return d


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
    # Cap per-section text seeded into the orchestrator prompt: the full prompt
    # is re-sent on every orchestrator turn, so embedding whole sections blows
    # the TPM budget on large chapters. Analysts work from these excerpts.
    _per_section_cap = int(os.environ.get("EXTENSION_SECTION_CHARS", "1200"))
    for r in range(rounds):
        if r == 0:
            seeded = "\n\n".join(
                f"=== {p} ===\n{c[:_per_section_cap]}"
                + ("\n…[truncated]" if len(c) > _per_section_cap else "")
                for p, c in structure.items()
            )
            instr = (
                "These /structure files hold the chapter sections:\n"
                f"{seed}\n\nSection excerpts follow:\n" + seeded +
                "\n\nRun the full pipeline: analyst per section -> polish -> "
                "plan queries -> augmentor. Then emit the ExtensionDigest JSON."
            )
        else:
            instr = (
                JUDGE_PROMPT
                + "\n\nSome gap queries are still unfilled. Acting as the Judge "
                "above: re-run the augmentor ONLY for the unfilled queries, then "
                "re-emit the ExtensionDigest JSON."
            )
        yield {"type": "stage", "stage": "augment", "label": f"Augment · round {r + 1}"}
        structured, text, unfilled, it, ot = await _run_round(agent, instr, thread_id)
        in_tok += it
        out_tok += ot
        if not unfilled:
            break

    # Prefer the schema-enforced structured_response; fall back to JSON-parsing
    # the final message only if the agent returned no structured output.
    digest = _coerce_digest(structured, book=book, chapter=chapter) \
        or _parse_digest(text, book=book, chapter=chapter)

    for pt in digest.points:
        if not curated_text_is_clean(pt):
            pt.curated_text = _AUG_LEAK.sub("", pt.curated_text).strip()
        # KaTeX mid-line $$ fix on curated body + every footnote body.
        pt.curated_text = _isolate_midline_display(pt.curated_text)
        for fn in pt.footnotes:
            fn.body = _isolate_midline_display(fn.body)

    for pt in digest.points:
        yield {"type": "stage", "stage": "point", "label": pt.title}
    yield {"type": "structured_output", "schema": "ExtensionDigest", "data": digest.model_dump()}
    yield {"type": "sources_full", "sources": []}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "inputTokens": in_tok, "outputTokens": out_tok}
    yield {"type": "done"}
