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
from src.services.chat.llm.router import aclient_for
from src.services.chat.prompts.chapter import (
    CHAPTER_GROUND_PROMPT,
    CHAPTER_MAP_FACILITATE_PROMPT,
    CHAPTER_MAP_RESUME_PROMPT,
    CHAPTER_PARSE_PROMPT,
    CHAPTER_RESOLVE_PROMPT,
    CHAPTER_STITCH_PROMPT,
)
from src.services.chat.retrieval import fetch_chapter_sections
from src.services.chat.schemas import (
    ChapterBlock,
    ChapterDigest,
    ChapterScope,
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
_CHUNK_PREVIEW_CHARS = 1500


def _model_for(stage: str, req: ChatRequest | None) -> str:
    """Resolve the model for a chapter stage: stageModels > env > nano."""
    sm = req.stageModels if req else None
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    env = os.environ.get(f"CHAPTER_{stage.upper()}_MODEL", "").strip()
    return env or settings.openai_model_nano


async def _chat(messages, *, model, max_tokens, temperature=0.0) -> str:
    """Single LLM seam. Returns the raw assistant content string."""
    oa = aclient_for(model)
    resp = await oa.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def parse_scope(
    message: str,
    *,
    book_slugs: list[str] | None,
    model: str | None = None,
) -> ChapterScope:
    """Extract {book_slug, chapter_id, requested_subtopics} from the message.

    Fail-open: a single selected book becomes book_slug; chapter "" and empty
    subtopics (whole chapter) on any parse error.
    """
    default_book = book_slugs[0] if book_slugs and len(book_slugs) == 1 else ""
    fallback = ChapterScope(book_slug=default_book, chapter_id="", requested_subtopics=[])
    chosen = model or settings.openai_model_nano
    try:
        raw = await _chat(
            [
                {"role": "system", "content": CHAPTER_PARSE_PROMPT},
                {"role": "user", "content": f"selected_books: {json.dumps(book_slugs or [])}\n\nmessage: {message}"},
            ],
            model=chosen,
            max_tokens=200,
        )
        data = json.loads(strip_fences(raw))
        return ChapterScope(
            book_slug=str(data.get("book_slug") or default_book).strip(),
            chapter_id=str(data.get("chapter_id") or "").strip(),
            requested_subtopics=[
                str(x).strip() for x in (data.get("requested_subtopics") or []) if str(x).strip()
            ],
        )
    except Exception:  # noqa: BLE001
        logger.exception("chapter.parse_scope failed; using fail-open scope")
        return fallback


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
) -> tuple[list[ChapterBlock], list[TutorCitation]]:
    """Generate one block per section, IN ORDER, threading a running summary.

    ``mode`` picks the prompt: "facilitate" -> teach, otherwise compress.
    Fail-open per section: on error the section excerpt becomes the body so the
    digest never has a hole.
    """
    sys_prompt = CHAPTER_MAP_FACILITATE_PROMPT if mode == "facilitate" else CHAPTER_MAP_RESUME_PROMPT
    chosen = model or settings.openai_model_nano
    blocks: list[ChapterBlock] = []
    all_citations: list[TutorCitation] = []
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
            )
            data = json.loads(strip_fences(raw))
            body = str(data.get("body", "")).strip() or (s.excerpt or "")
            cites = _coerce_citations(data.get("citations"))
        except Exception:  # noqa: BLE001
            logger.exception("chapter.map_sections failed at %s; using excerpt", s.chunkId)
            body, cites = (s.excerpt or ""), []

        blocks.append(ChapterBlock(
            h2_path=s.title, section_id=s.chunkId, body=body,
            page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1,
        ))
        all_citations.extend(cites)
        prior_context = (prior_context + " " + body)[-240:]

    return blocks, all_citations


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
