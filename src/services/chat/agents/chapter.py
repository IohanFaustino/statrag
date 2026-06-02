"""Chapter modes agent: facilitate (teach) + resume (compress).

Shared pipeline: parse-scope -> fetch-chapter -> resolve-subtopics ->
map(per-section, in order) -> stitch -> ground. Order is fixed structurally
by ``fetch_chapter_sections`` before any LLM runs. The two modes differ only
in which MAP prompt is used.

Each LLM node goes through the single ``_chat`` seam so tests monkeypatch one
function. Emits the v1 SSE event schema.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents._scope import maybe_clarify, resolve_book
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.llm.structured import apply_structured_output
from src.services.chat.prompts.chapter import (
    CHAPTER_GROUND_PROMPT,
    CHAPTER_MAP_RESUME_PROMPT,
    CHAPTER_PARSE_PROMPT,
    CHAPTER_RESOLVE_PROMPT,
    CHAPTER_STITCH_PROMPT,
)
from src.services.chat.retrieval import fetch_chapter_sections
from src.services.chat.schemas import (
    BookResolution,
    CatalogBook,
    ChapterBlock,
    ChapterDigest,
    ChapterGroundOut,
    ChapterMapBlock,
    ChapterResolveMatches,
    ChapterScope,
    ChapterStitchOut,
    ChatRequest,
    ResolvedSubtopic,
    Source,
    TutorCitation,
)

logger = logging.getLogger(__name__)

_CHAPTER_RESOLVE = os.environ.get("CHAPTER_RESOLVE", "1") == "1"
_CHAPTER_MAX_SECTIONS = int(os.environ.get("CHAPTER_MAX_SECTIONS", "30"))
_CHAPTER_STITCH = os.environ.get("CHAPTER_STITCH", "1") == "1"
_CHAPTER_GROUND = os.environ.get("CHAPTER_GROUND", "1") == "1"
_CHAPTER_CLARIFY = os.environ.get("CHAPTER_CLARIFY", "1") == "1"
_CHUNK_PREVIEW_CHARS = 1500


def _model_for(stage: str, req: ChatRequest | None) -> str:
    """Resolve the model for a chapter stage: stageModels > env > nano."""
    sm = req.stageModels if req else None
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    env = os.environ.get(f"CHAPTER_{stage.upper()}_MODEL", "").strip()
    return env or settings.openai_model_nano


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam. Returns the raw assistant content string.

    Intentionally duplicated per module (not extracted): tests monkeypatch each module's ``_chat`` independently, so a shared helper would collapse those seams.
    """
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs: dict = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_completion_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


async def parse_scope(
    message: str,
    *,
    book_slugs: list[str] | None,
    model: str | None = None,
    catalog: list[CatalogBook] | None = None,
) -> ChapterScope:
    """Resolve scope via the shared catalog-in-prompt resolver (thin wrapper)."""
    cat = catalog if catalog is not None else parse_catalog()
    res: BookResolution = await resolve_book(
        message, selected_slugs=book_slugs, catalog=cat, model=model)
    return ChapterScope(
        book_slug=res.book_slug,
        chapter_id=res.chapter_id,
        requested_subtopics=res.requested_subtopics,
    )


def _section_index(sections: list[Source]) -> dict[str, Source]:
    """Map section_id (chunkId) -> Source for selection by id."""
    return {s.chunkId: s for s in sections}


async def resolve_subtopics(
    requested: list[str],
    sections: list[Source],
    *,
    model: str | None = None,
) -> tuple[list[Source], list[ResolvedSubtopic]]:
    """Map requested subtopic phrases to fetched sections (closest-match).

    Empty ``requested`` -> the whole chapter in fetched order, no resolution
    entries. Otherwise: case-insensitive substring match first; any phrase
    that still has no hit is resolved by one nano call. Selection preserves the
    fetched order; duplicates are de-duplicated.
    """
    if not requested:
        return list(sections), []

    by_id = _section_index(sections)
    resolution: list[ResolvedSubtopic] = []
    matched_ids: set[str] = set()
    unmatched: list[str] = []

    for phrase in requested:
        low = phrase.lower().strip()
        hit = next((s for s in sections if low in s.title.lower()), None)
        if hit is not None:
            resolution.append(ResolvedSubtopic(
                asked=phrase, matched_h2=hit.title, section_id=hit.chunkId, score=0.95))
            matched_ids.add(hit.chunkId)
        else:
            unmatched.append(phrase)

    if unmatched and _CHAPTER_RESOLVE:
        headings = [{"section_id": s.chunkId, "h2_path": s.title} for s in sections]
        try:
            raw = await _chat(
                [
                    {"role": "system", "content": CHAPTER_RESOLVE_PROMPT},
                    {"role": "user", "content": json.dumps({"requested": unmatched, "headings": headings})},
                ],
                model=model or settings.openai_model_nano,
                max_tokens=400,
                schema=ChapterResolveMatches,
            )
            data = json.loads(strip_fences(raw))
            for m in data.get("matches", []):
                sid = str(m.get("section_id") or "")
                if sid and sid in by_id:
                    resolution.append(ResolvedSubtopic(
                        asked=str(m.get("asked", "")),
                        matched_h2=str(m.get("matched_h2") or by_id[sid].title),
                        section_id=sid,
                        score=float(m.get("score", 0.5)),
                    ))
                    matched_ids.add(sid)
                else:
                    resolution.append(ResolvedSubtopic(asked=str(m.get("asked", ""))))
        except Exception:  # noqa: BLE001
            logger.exception("chapter.resolve_subtopics LLM step failed")
            for phrase in unmatched:
                resolution.append(ResolvedSubtopic(asked=phrase))

    selected = [s for s in sections if s.chunkId in matched_ids]
    return selected, resolution


def _coerce_citations(raw: list) -> list[TutorCitation]:
    """Build TutorCitation list defensively from model JSON."""
    out: list[TutorCitation] = []
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        try:
            out.append(TutorCitation(
                index=int(c.get("index", len(out) + 1)),
                chunkId=str(c.get("chunkId", "")),
                authors_short=str(c.get("authors_short", "")),
                year=c.get("year") if isinstance(c.get("year"), int) else None,
                book_name=str(c.get("book_name", "")),
                chapter=str(c.get("chapter", "")),
                section=str(c.get("section", "")),
                quote=str(c.get("quote", "")),
            ))
        except Exception:  # noqa: BLE001
            continue
    return out


async def map_sections(
    sections: list[Source],
    *,
    mode: str,
    model: str | None = None,
) -> tuple[list[ChapterBlock], list[TutorCitation], list[str]]:
    """Generate one block per section, IN ORDER, threading a running summary.

    ``mode`` picks the prompt: "facilitate" -> teach, otherwise compress.
    Fail-open per section: on error the section excerpt becomes the body so the
    digest never has a hole.

    Returns a 3-tuple: (blocks, citations, math_blocks).
    """
    sys_prompt = CHAPTER_MAP_RESUME_PROMPT
    chosen = model or settings.openai_model_nano
    blocks: list[ChapterBlock] = []
    all_citations: list[TutorCitation] = []
    all_math: list[str] = []
    prior_context = ""

    for i, s in enumerate(sections, 1):
        body_text = (s.chunk or s.excerpt or "")[:_CHUNK_PREVIEW_CHARS]
        user = (
            f"heading: {s.title}\n"
            f"prior_context: {prior_context}\n\n"
            f"section text:\n[{i}] {body_text}"
        )
        try:
            raw = await _chat(
                [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                model=chosen,
                max_tokens=900,
                schema=ChapterMapBlock,
            )
            data = json.loads(strip_fences(raw))
            body = str(data.get("body", "")).strip() or (s.excerpt or "")
            cites = _coerce_citations(data.get("citations"))
            math = [str(m) for m in (data.get("math_blocks") or []) if str(m).strip()]
        except Exception:  # noqa: BLE001
            logger.exception("chapter.map_sections failed at %s; using excerpt", s.chunkId)
            body, cites, math = (s.excerpt or ""), [], []

        blocks.append(ChapterBlock(
            h2_path=s.title, section_id=s.chunkId, body=body,
            page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1,
        ))
        all_citations.extend(cites)
        all_math.extend(math)
        prior_context = (prior_context + " " + body)[-240:]

    return blocks, all_citations, all_math


def _sources_block(sources: list[Source]) -> str:
    lines = []
    for i, s in enumerate(sources, 1):
        body = (s.chunk or s.excerpt or "")[:_CHUNK_PREVIEW_CHARS]
        lines.append(f"[{i}] {s.book_name or s.book} · {s.chapter} {s.section} — {s.title}\n{body}")
    return "\n\n".join(lines)


async def stitch(blocks: list[ChapterBlock], *, model: str | None = None) -> tuple[str, str]:
    """Generate a short intro/outro. Fail-open: empty strings on error."""
    if not blocks:
        return "", ""
    headings = [b.h2_path for b in blocks]
    try:
        raw = await _chat(
            [
                {"role": "system", "content": CHAPTER_STITCH_PROMPT},
                {"role": "user", "content": json.dumps({"headings": headings})},
            ],
            model=model or settings.openai_model_nano,
            max_tokens=200,
            schema=ChapterStitchOut,
        )
        data = json.loads(strip_fences(raw))
        return str(data.get("intro", "")).strip(), str(data.get("outro", "")).strip()
    except Exception:  # noqa: BLE001
        logger.exception("chapter.stitch failed; empty intro/outro")
        return "", ""


async def ground(
    blocks: list[ChapterBlock],
    sources: list[Source],
    *,
    model: str | None = None,
) -> dict:
    """Audit the digest against sources. Advisory; fail-open marks low confidence."""
    body = "\n\n".join(b.body for b in blocks)
    try:
        raw = await _chat(
            [
                {"role": "system", "content": CHAPTER_GROUND_PROMPT},
                {"role": "user", "content": f"digest:\n{body}\n\nsources:\n{_sources_block(sources)}"},
            ],
            model=model or settings.openai_model_nano,
            max_tokens=500,
            schema=ChapterGroundOut,
        )
        data = json.loads(strip_fences(raw))
        return {
            "ok": bool(data.get("ok", False)),
            "unsupported": [str(x) for x in (data.get("unsupported") or [])],
            "confidence": float(data.get("confidence", 0.5)),
        }
    except Exception:  # noqa: BLE001
        logger.exception("chapter.ground failed; low confidence")
        return {"ok": False, "unsupported": [], "confidence": 0.5}


async def run_chapter(req: ChatRequest) -> AsyncIterator[dict]:
    """Execute the chapter pipeline and yield v1 SSE event dicts."""
    t0 = time.time()
    mode = req.mode if req.mode in ("facilitate", "resume") else "resume"
    message = req.message or ""
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {
        "type": "meta", "mode": mode, "books": book_slugs or [],
        "sourceCount": 0, "latencyMs": int((time.time() - t0) * 1000), "model": req.model,
    }

    # 1. parse + resolve scope (catalog-in-prompt)
    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}
    catalog = parse_catalog()
    res = await resolve_book(
        message, selected_slugs=book_slugs, catalog=catalog,
        model=_model_for("parse", req))
    scope = ChapterScope(
        book_slug=res.book_slug, chapter_id=res.chapter_id,
        requested_subtopics=res.requested_subtopics)

    # confirm gate — fire clarify only on ambiguity/miss
    if _CHAPTER_CLARIFY:
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar
            yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
                   "promptChars": len(message), "completionChars": 0, "estTokens": 0}
            yield {"type": "done"}
            return

    # 2. fetch chapter (structural, ordered)
    yield {"type": "stage", "stage": "fetch", "label": "Fetch chapter"}
    try:
        sections = (
            fetch_chapter_sections(scope.book_slug, scope.chapter_id, max_sections=_CHAPTER_MAX_SECTIONS)
            if scope.book_slug and scope.chapter_id else []
        )
    except Exception:  # noqa: BLE001
        logger.exception("chapter.run_chapter: fetch failed; treating as chapter-not-found")
        sections = []

    if not sections:
        digest = ChapterDigest(
            mode=mode, scope=scope, blocks=[],
            intro=("Chapter not found in the selected books. Pick a book and name a "
                   "chapter (e.g. 'ch02')."),
            grounding={"ok": True, "unsupported": [], "confidence": 1.0},
        )
        yield {"type": "structured_output", "schema": "ChapterDigest", "data": digest.model_dump()}
        yield {"type": "sources_full", "sources": []}
        yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
               "promptChars": len(message), "completionChars": len(digest.intro),
               "estTokens": (len(message) + len(digest.intro)) // 4}
        yield {"type": "done"}
        return

    # 3. resolve subtopics -> selected ordered sections
    yield {"type": "stage", "stage": "resolve", "label": "Resolve subtopics"}
    if scope.requested_subtopics and _CHAPTER_RESOLVE:
        selected, resolution = await resolve_subtopics(
            scope.requested_subtopics, sections, model=_model_for("resolve", req))
    else:
        selected, resolution = list(sections), []
    scope = scope.model_copy(update={"resolution": resolution})
    if not selected:  # all requested names dropped -> fall back to whole chapter
        selected = list(sections)

    try:
        # 4. map per-section, in order
        for s in selected:
            yield {"type": "stage", "stage": "map", "label": f"Map · {s.section}"}
        blocks, citations, math_blocks = await map_sections(selected, mode=mode, model=_model_for("map", req))

        # 5. stitch
        intro, outro = "", ""
        if _CHAPTER_STITCH:
            yield {"type": "stage", "stage": "stitch", "label": "Stitch"}
            intro, outro = await stitch(blocks, model=_model_for("stitch", req))

        # 6. ground (advisory)
        grounding = {"ok": True, "unsupported": [], "confidence": 0.7}
        if _CHAPTER_GROUND:
            yield {"type": "stage", "stage": "ground", "label": "Ground"}
            grounding = await ground(blocks, selected, model=_model_for("ground", req))
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
        return

    digest = ChapterDigest(
        mode=mode, scope=scope, intro=intro, blocks=blocks, outro=outro,
        citations=citations, math_blocks=math_blocks, grounding=grounding,
    )

    yield {"type": "structured_output", "schema": "ChapterDigest", "data": digest.model_dump()}
    yield {
        "type": "sources_full",
        "sources": [
            {
                "rank": s.rank, "book": s.book, "book_name": s.book_name or s.book,
                "authors_short": s.authors_short, "year": s.year,
                "chapter": s.chapter, "section": s.section, "title": s.title,
                "excerpt": s.excerpt, "chunk": (s.chunk or "")[:_CHUNK_PREVIEW_CHARS],
                "score": round(float(s.score), 4), "chunkId": s.chunkId,
            }
            for s in selected
        ],
    }
    yield {
        "type": "usage", "durationMs": int((time.time() - t0) * 1000),
        "promptChars": len(message),
        "completionChars": sum(len(b.body) for b in blocks),
        "estTokens": (len(message) + sum(len(b.body) for b in blocks)) // 4,
    }
    yield {"type": "done"}
