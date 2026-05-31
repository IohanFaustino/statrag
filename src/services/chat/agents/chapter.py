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
