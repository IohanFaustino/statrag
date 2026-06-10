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

# Matches a leading section number like "7.4" or "7.4.1" from a section label.
_SECTION_NUM_PREFIX = _re.compile(r'^(\d+(?:[.\-]\d+)+)')


def _extract_section_num(section_id: str) -> str | None:
    """Extract the leading dotted/dashed section number from a section label.

    Examples::

        "7.4 Chebyshev Inequality" -> "7.4"
        "7.4.1 Sub-section"        -> "7.4.1"
        "Introduction"             -> None
    """
    m = _SECTION_NUM_PREFIX.match(section_id.strip())
    return m.group(1) if m else None


def _scope_label(chapter_id: str, sections: list[dict], *, narrowed: bool) -> str:
    """Derive a human-readable chapter/section label for the digest header.

    When *narrowed* is True and sections carry recognisable numeric section
    numbers (e.g. ``"7.4 Chebyshev Inequality"``), the label is:

    * single section  → ``"{chapter_id} · 7.4"``
    * multiple        → ``"{chapter_id} · 7.4–7.5"``

    When not narrowed (all sections kept), or when numeric prefixes cannot be
    extracted, the label is just *chapter_id* (e.g. ``"ch07"``).
    """
    if not narrowed or not sections:
        return chapter_id
    nums = [_extract_section_num(str(s.get("section_id", ""))) for s in sections]
    nums = [n for n in nums if n]
    if not nums:
        return chapter_id
    if len(nums) == 1:
        return f"{chapter_id} · {nums[0]}"
    return f"{chapter_id} · {nums[0]}–{nums[-1]}"

from src.services.chat.agents.extension_agents.agent import build_extension_agent
from src.services.chat.agents.extension_agents.scope import (
    aresolve_scope_or_clarify,
    build_structure_files,
)
from src.services.chat._fences import strip_fences
from src.services.chat.agents.extension_agents.prompts import JUDGE_PROMPT
from src.services.chat.books import parse_catalog
from src.services.chat.retrieval import fetch_chapter_sections, hybrid_search
from src.services.chat.schemas import ChatRequest, ExtensionDigest


def _warm_retrieval(slugs: list[str]) -> None:
    """Initialise the dense + sparse embedders (and tqdm's lock) on the MAIN
    thread. The augmentor later calls retrieve_corpus inside a worker thread
    (asyncio.to_thread), where fastembed's first-use tqdm/torch init raises
    ("tqdm has no attribute '_lock'", reranker meta-tensor). Warming here means
    the cached embedders are reused in-thread without re-initialising."""
    try:
        hybrid_search("warmup", book_slugs=slugs or None, top_k=1, rerank=False)
    except Exception:  # noqa: BLE001
        pass


_AUG_LEAK = _re.compile(r"https?://|\[source\]|en\.wikipedia\.org", _re.IGNORECASE)
_LATEX_PAREN = _re.compile(r'\\\((.+?)\\\)', _re.DOTALL)
_LATEX_BRACKET = _re.compile(r'\\\[(.+?)\\\]', _re.DOTALL)
_MD_FOOTNOTE = _re.compile(r'\[\^[^\]]+\]')


def _normalize_math_delimiters(text: str) -> str:
    r"""Convert \(...\) → $...$ and \[...\] → $$...$$ (own line).
    Applied to curated_text and footnote bodies before emit so the
    export ZIP and any consumer sees KaTeX-ready delimiters."""
    if not text:
        return text
    text = _LATEX_BRACKET.sub(lambda m: f'\n$$\n{m.group(1)}\n$$\n', text)
    text = _LATEX_PAREN.sub(lambda m: f'${m.group(1)}$', text)
    return text


def _strip_md_footnote_markers(text: str) -> str:
    r"""Remove [^n] markdown footnote markers from curated_text.
    These render literally in React; footnotes use the ExtensionFootnote.marker field."""
    return _MD_FOOTNOTE.sub('', text) if text else text


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


def _needle_matches(needle: str, haystack: str) -> bool:
    """Return True when *needle* occurs in *haystack* with word-boundary
    protection for section numbers.

    Strategy:
    1. If the needle begins with a section number (e.g. ``"7.4"`` or
       ``"7.4 Chebyshev"``), match by that section-number prefix using a
       word-boundary regex — this avoids false-positives like ``"7.4"``
       matching ``"17.4"``, and correctly handles acronym-titled sections
       where the label text differs from the needle's keyword suffix.
    2. If no section-number prefix is found, fall back to plain substring
       matching.
    """
    m = _SECTION_NUM_PREFIX.match(needle)
    if m:
        sec_num = m.group(1)
        # Word-boundary: the number must not be immediately preceded/followed
        # by another digit or dot (so "7.4" won't match "17.4" or "7.40").
        pattern = r'(?<![.\d])' + _re.escape(sec_num) + r'(?![.\d])'
        return bool(_re.search(pattern, haystack))
    return needle in haystack


def _filter_subtopics(
    sections: list[dict], subtopics: list[str], *, book_slug: str = ""
) -> list[dict]:
    clean = [t for t in subtopics if t and t.strip()]
    if not clean:
        return sections
    needles = [t.lower() for t in clean]
    # Fast path: exact/substring match on h2_path + section_id.
    kept = [
        s for s in sections
        if any(
            _needle_matches(
                n,
                (str(s.get("h2_path", "")) + " " + str(s.get("section_id", ""))).lower(),
            )
            for n in needles
        )
    ]
    if kept:
        return kept
    # Fallback: embedding-based fuzzy match via hybrid_search.
    matched_ids: set[str] = set()
    slugs = [book_slug] if book_slug else None
    for needle in clean:
        try:
            rows, _ = hybrid_search(needle, book_slugs=slugs, top_k=3, rerank=False)
            for r in rows:
                sid = (
                    getattr(r, "section", "")
                    or getattr(r, "section_id", "")
                    or ""
                )
                if sid:
                    matched_ids.add(sid)
        except Exception:  # noqa: BLE001
            pass
    fuzzy_kept = [s for s in sections if str(s.get("section_id", "")) in matched_ids]
    return fuzzy_kept or sections  # final fallback: whole chapter


async def _run_round(agent, instruction: str, thread_id: str):
    """Invoke the deep-agent for one round. Returns
    (structured_response, final_text, unfilled_queries, in_tok, out_tok).

    structured_response is the schema-enforced ExtensionDigest (deepagents
    response_format=ToolStrategy(ExtensionDigest)); text is the fallback when it
    is absent."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler
    cb = UsageMetadataCallbackHandler()
    # The quality pipeline (≥2 gaps/section, ≥2 footnotes/point, per-source fit
    # scoring) needs far more graph super-steps than langgraph's default 25.
    recursion_limit = int(os.environ.get("EXTENSION_RECURSION_LIMIT", "100"))
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": instruction}]},
        {"configurable": {"thread_id": thread_id}, "callbacks": [cb],
         "recursion_limit": recursion_limit},
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
    into an ExtensionDigest, stamping authoritative book/chapter unconditionally.

    The model frequently emits ``book="Unknown"`` or widens the chapter range
    (e.g. ``"7.4–7.8"`` when only 7.4–7.5 were requested).  The runner holds
    the resolved scope and is always authoritative for these two fields."""
    if structured is None:
        return None
    try:
        d = structured if isinstance(structured, ExtensionDigest) else ExtensionDigest(
            **(structured if isinstance(structured, dict) else structured.model_dump())
        )
    except Exception:  # noqa: BLE001
        return None
    # Always override — never trust the model's book/chapter values.
    d.book = book
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
    """Parse the agent's final text as a JSON ExtensionDigest.

    Authoritative book/chapter are always stamped after parsing — the model
    cannot be trusted to return the correct scope values."""
    raw = strip_fences(text)
    try:
        data = json.loads(raw)
        d = ExtensionDigest(**data)
    except Exception:  # noqa: BLE001
        d = ExtensionDigest(book=book, chapter=chapter, points=[],
                            unfilled_gaps=["could not parse agent output"])
    # Always override — never trust the model's book/chapter values.
    d.book = book
    d.chapter = chapter
    return d


async def run_extension(req: ChatRequest) -> AsyncIterator[dict]:
    t0 = time.time()
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else []
    yield {"type": "meta", "mode": "extension", "books": book_slugs,
           "sourceCount": 0, "latencyMs": 0, "model": req.model}
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
    all_sections = [_section_to_dict(s) for s in raw_sections]
    sections = _filter_subtopics(all_sections, res.requested_subtopics, book_slug=book)
    narrowed = bool(res.requested_subtopics) and len(sections) < len(all_sections)
    chapter_label = _scope_label(chapter, sections, narrowed=narrowed)
    structure = build_structure_files(sections)

    slugs = _all_slugs(catalog)
    _warm_retrieval([s for s in slugs if s != book])  # main-thread embedder init
    seen_chunk_ids: set[str] = set()
    agent = build_extension_agent(stage_models=req.extensionModels,
                                  exclude_book=book, all_slugs=slugs,
                                  seen_ids=seen_chunk_ids)
    thread_id = f"ext-{book}-{chapter}-{int(t0)}"

    seed = "\n".join(f"- {p}" for p in structure.keys())
    in_tok = out_tok = 0
    text = ""
    rounds = _max_rounds(req)
    # Cap per-section text seeded into the orchestrator prompt: the full prompt
    # is re-sent on every orchestrator turn, so embedding whole sections blows
    # the TPM budget on large chapters. Analysts work from these excerpts.
    _per_section_cap = int(os.environ.get("EXTENSION_SECTION_CHARS", "2500"))
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
    digest = _coerce_digest(structured, book=book, chapter=chapter_label) \
        or _parse_digest(text, book=book, chapter=chapter_label)

    for pt in digest.points:
        if not curated_text_is_clean(pt):
            pt.curated_text = _AUG_LEAK.sub("", pt.curated_text).strip()
        pt.title = _normalize_math_delimiters(pt.title)
        pt.curated_text = _isolate_midline_display(pt.curated_text)
        pt.curated_text = _normalize_math_delimiters(pt.curated_text)
        pt.curated_text = _strip_md_footnote_markers(pt.curated_text)
        for fn in pt.footnotes:
            fn.body = _isolate_midline_display(fn.body)
            fn.body = _normalize_math_delimiters(fn.body)
    digest.unfilled_gaps = [_normalize_math_delimiters(g) for g in digest.unfilled_gaps]

    for pt in digest.points:
        yield {"type": "stage", "stage": "point", "label": pt.title}
    yield {"type": "structured_output", "schema": "ExtensionDigest", "data": digest.model_dump()}
    yield {"type": "sources_full", "sources": []}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "inputTokens": in_tok, "outputTokens": out_tok}
    yield {"type": "done"}
