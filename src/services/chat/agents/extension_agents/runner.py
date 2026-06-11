"""Extension-mode runner: SSE wrapper around the deterministic v2 pipeline.

Chinese-wall: src.core.* + sibling extension_agents + shared chat infra only."""
from __future__ import annotations

import asyncio
import logging
import re as _re
import time
from typing import AsyncIterator

from src.services.chat.agents.extension_agents.graph import run_pipeline
from src.services.chat.agents.extension_agents.scope import aresolve_scope_or_clarify
from src.services.chat.books import parse_catalog
from src.services.chat.research import _isolate_midline_display  # re-export from shared module
from src.services.chat.retrieval import fetch_chapter_sections, hybrid_search
from src.services.chat.schemas import ChatRequest

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Sentinel for lazy package-logger configuration (set once inside run_extension
# to avoid mutating global logger state at import/collection time — pytest
# collection of this module must not cause extension INFO records to leak into
# other tests' caplog).
_pkg_log_configured = False

_PKG_LOGGER_NAME = "src.services.chat.agents.extension_agents"


def _ensure_pkg_logging() -> None:
    """Ensure INFO records from the extension_agents package reach the console.

    Under uvicorn's default config the root logger has NO real handler — only
    ``logging.lastResort`` (level WARNING), so propagated INFO records are
    silently dropped.  This function (called once, lazily) attaches a
    StreamHandler directly to the package logger when neither it nor any
    ancestor already has a real handler, and sets ``propagate = False`` to
    prevent future double-printing if a parent logger later gains a handler.

    The function is idempotent when called multiple times; the module-level
    ``_pkg_log_configured`` sentinel prevents duplicate calls from
    ``run_extension``, but the function itself is safe to call directly in
    tests via the sentinel reset.
    """
    pkg = logging.getLogger(_PKG_LOGGER_NAME)
    pkg.setLevel(logging.INFO)

    # Walk up the logger hierarchy to check for real (non-lastResort) handlers.
    node: logging.Logger | logging.PlaceHolder | None = pkg
    has_real_handler = False
    while isinstance(node, logging.Logger):
        if node.handlers:
            has_real_handler = True
            break
        if not node.propagate:
            break
        parent_name = node.name.rsplit(".", 1)[0] if "." in node.name else ""
        node = logging.getLogger(parent_name) if parent_name else logging.root
        if node is logging.root:
            if node.handlers:
                has_real_handler = True
            break

    if not has_real_handler:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        pkg.addHandler(handler)
        pkg.propagate = False

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


def _warm_retrieval(slugs: list[str]) -> None:
    """Initialise the dense + sparse embedders AND the cross-encoder reranker on the MAIN thread.

    The pipeline calls corpus_evidence inside asyncio.to_thread; warming here
    means the cached embedders AND the reranker are materialised on the main
    thread.  The reranker (CrossEncoderReranker) uses @cached_property on its
    _model and a module-level singleton (_REGISTRY / get_reranker()), so a
    main-thread load persists the loaded weights on the shared singleton
    instance — subsequent worker-thread calls access the already-materialised
    _model attribute without re-loading.  Without this warm-up, the
    CrossEncoder's lazy load inside asyncio.to_thread worker threads triggers a
    torch meta-tensor crash (transformers modeling_utils.to() on an uninitialised
    device context)."""
    try:
        hybrid_search("warmup", book_slugs=slugs or None, top_k=1, rerank=True, rerank_top_n=1)
    except Exception:  # noqa: BLE001
        pass


_LATEX_PAREN = _re.compile(r'\\\((.+?)\\\)', _re.DOTALL)
_LATEX_BRACKET = _re.compile(r'\\\[(.+?)\\\]', _re.DOTALL)


def _normalize_math_delimiters(text: str) -> str:
    r"""Convert \(...\) → $...$ and \[...\] → $$...$$ (own line)."""
    if not text:
        return text
    text = _LATEX_BRACKET.sub(lambda m: f'\n$$\n{m.group(1)}\n$$\n', text)
    text = _LATEX_PAREN.sub(lambda m: f'${m.group(1)}$', text)
    return text


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
    protection for section numbers."""
    sec_num = _extract_section_num(needle)
    if sec_num:
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


# ---------------------------------------------------------------------------
# v2 SSE entry point
# ---------------------------------------------------------------------------

async def run_extension(req: ChatRequest) -> AsyncIterator[dict]:
    # Ensure diagnostic INFO logs from the extension_agents package reach the
    # uvicorn console.  See _ensure_pkg_logging() for full rationale.
    global _pkg_log_configured
    if not _pkg_log_configured:
        _ensure_pkg_logging()
        _pkg_log_configured = True

    t0 = time.time()
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else []
    yield {"type": "meta", "mode": "extension", "books": book_slugs,
           "sourceCount": 0, "latencyMs": 0, "model": req.model}
    yield {"type": "stage", "stage": "parse", "label": "Resolve scope"}
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

    book, chapter = res.book_slug, res.chapter_id
    yield {"type": "stage", "stage": "fetch", "label": f"Fetch {book} {chapter}"}
    all_sections = [_section_to_dict(s) for s in
                    fetch_chapter_sections(book_slug=book, chapter_id=chapter)]
    sections = _filter_subtopics(all_sections, res.requested_subtopics, book_slug=book)
    narrowed = bool(res.requested_subtopics) and len(sections) < len(all_sections)
    chapter_label = _scope_label(chapter, sections, narrowed=narrowed)

    slugs = _all_slugs(catalog)
    _warm_retrieval([s for s in slugs if s != book])   # embedder+reranker on main thread

    stage_q: asyncio.Queue[dict] = asyncio.Queue()

    def on_stage(key: str, label: str) -> None:
        stage_q.put_nowait({"type": "stage", "stage": key, "label": label})

    task = asyncio.create_task(run_pipeline(
        book=book, chapter_label=chapter_label, sections=sections,
        all_slugs=slugs, stage_models=req.extensionModels, on_stage=on_stage))
    while not task.done() or not stage_q.empty():
        try:
            yield await asyncio.wait_for(stage_q.get(), timeout=0.25)
        except asyncio.TimeoutError:
            continue
    digest, evidence = await task

    for pt in digest.takes:          # delimiter safety net
        pt.heading = _normalize_math_delimiters(pt.heading)
        pt.story = _normalize_math_delimiters(_isolate_midline_display(pt.story))
        for it in pt.items:
            it.body = _normalize_math_delimiters(_isolate_midline_display(it.body))

    yield {"type": "structured_output", "schema": "StoryDigest",
           "data": digest.model_dump()}
    # Map evidence metas to the frontend Source contract so ContextPanel/SourceCard
    # never dereferences an undefined field (e.g. src.book.toLowerCase() crashes
    # when book is absent from raw evidence meta).
    sources = []
    for i, e in enumerate(evidence, start=1):
        m = e.meta if isinstance(e.meta, dict) else {}
        book_key = (
            m.get("book_slug")
            or ("wikipedia" if getattr(e, "kind", "") == "wikipedia" else "corpus")
        )
        sources.append({
            "rank": i,
            "book": str(book_key),
            "chapter": str(m.get("chapter") or ""),
            "section": str(m.get("section_id") or m.get("title") or ""),
            "title": str(m.get("title") or m.get("section_id") or ""),
            "excerpt": str(getattr(e, "text", "") or "")[:280],
            "score": 0.0,
            "chunkId": str(m.get("chunk_id") or ""),
            "embedding": "",
            "chunk": "",
            "highlights": [],
        })
    yield {"type": "sources_full", "sources": sources}
    # token counting not yet wired for v2 pipeline — placeholder zeros
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "inputTokens": 0, "outputTokens": 0}
    yield {"type": "done"}
