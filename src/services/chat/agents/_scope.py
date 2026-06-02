"""Shared book/chapter/section scope resolver for chapter + qa modes.

Catalog-in-prompt: the parse LLM is given a compact book catalog so fuzzy,
paraphrased, or author-only references resolve to a slug with a confidence.
Numeric section refs ("7.2 up to 7.4") are expanded deterministically here,
never left to the LLM.

Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import json
import logging
import os
import re

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.schemas import BookResolution, CatalogBook

logger = logging.getLogger(__name__)

_SEC = re.compile(r"\b(\d+)\.(\d+)\b")


def expand_section_refs(text: str) -> list[str]:
    """Extract section numbers, expanding "X.a up to/-/through X.b" ranges.

    Returns ordered, de-duplicated "X.y" strings. Empty if none found.
    """
    nums = _SEC.findall(text or "")
    if not nums:
        return []
    is_range = bool(re.search(r"(up to|through|to|[-–—])", text))
    pairs = [(int(a), int(b)) for a, b in nums]
    out: list[str] = []
    if is_range and len(pairs) >= 2 and pairs[0][0] == pairs[-1][0]:
        chap = pairs[0][0]
        lo, hi = pairs[0][1], pairs[-1][1]
        if lo <= hi:
            out = [f"{chap}.{i}" for i in range(lo, hi + 1)]
    if not out:
        out = [f"{a}.{b}" for a, b in pairs]
    seen: set[str] = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


# ---------------------------------------------------------------------------
# Catalog-in-prompt resolver
# ---------------------------------------------------------------------------

from src.services.chat.llm.router import aclient_for  # noqa: E402
from src.services.chat.llm.structured import apply_structured_output  # noqa: E402
from src.services.chat.prompts.chapter import CHAPTER_PARSE_PROMPT  # noqa: E402
from src.services.chat.schemas import ChapterParse  # noqa: E402


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam (tests monkeypatch this)."""
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


def _catalog_payload(catalog: list[CatalogBook]) -> list[dict]:
    return [c.model_dump() for c in catalog]


async def resolve_book(
    message: str,
    *,
    selected_slugs: list[str] | None,
    catalog: list[CatalogBook],
    model: str | None = None,
) -> BookResolution:
    """Resolve {book, chapter, subtopics} from a fuzzy request via catalog-in-prompt."""
    single = selected_slugs[0] if selected_slugs and len(selected_slugs) == 1 else ""
    sections = expand_section_refs(message)
    fallback = BookResolution(
        book_slug=single,
        book_confidence=1.0 if single else 0.0,
        book_candidates=[single] if single else [],
        chapter_id="",
        requested_subtopics=sections,
    )
    chosen = model or settings.openai_model_nano
    try:
        raw = await _chat(
            [
                {"role": "system", "content": CHAPTER_PARSE_PROMPT},
                {"role": "user", "content": json.dumps({
                    "catalog": _catalog_payload(catalog),
                    "selected_slugs": selected_slugs or [],
                    "message": message,
                })},
            ],
            model=chosen, max_tokens=300, schema=ChapterParse,
        )
        data = json.loads(strip_fences(raw))
        valid = {c.slug for c in catalog}
        slug = str(data.get("book_slug") or single).strip()
        if slug and slug not in valid:
            slug = ""
        cands = [str(s).strip() for s in (data.get("book_candidates") or []) if str(s).strip() in valid]
        if single:
            slug = single
            cands = [single]
        subtopics = [str(x).strip() for x in (data.get("requested_subtopics") or []) if str(x).strip()]
        subtopics = sections + [s for s in subtopics if s not in sections]
        return BookResolution(
            book_slug=slug,
            book_confidence=1.0 if single else float(data.get("book_confidence", 0.0)),
            book_candidates=cands or ([slug] if slug else []),
            chapter_id=str(data.get("chapter_id") or "").strip(),
            requested_subtopics=subtopics,
        )
    except Exception:  # noqa: BLE001
        logger.exception("_scope.resolve_book failed; fail-open")
        return fallback


# ---------------------------------------------------------------------------
# Confirm gate
# ---------------------------------------------------------------------------

_BOOK_CONFIRM_CUTOFF = float(os.environ.get("BOOK_CONFIRM_CUTOFF", "0.6"))


def _candidate_records(slugs: list[str], catalog: list[CatalogBook]) -> list[dict]:
    by = {c.slug: c for c in catalog}
    out = []
    for s in slugs:
        c = by.get(s)
        if c:
            out.append({"slug": c.slug, "name": c.name,
                        "authors_short": c.authors_short, "chapters": c.chapters})
    return out


def maybe_clarify(res: BookResolution, catalog: list[CatalogBook]) -> dict | None:
    """Return a clarify event dict, or None to proceed. Ambiguity/miss only."""
    by = {c.slug: c for c in catalog}
    reason = ""
    cand_slugs = res.book_candidates or ([res.book_slug] if res.book_slug else [])
    if not res.book_slug:
        reason = "book_ambiguous" if len(cand_slugs) >= 2 else "book_unknown"
    elif res.book_confidence < _BOOK_CONFIRM_CUTOFF:
        reason = "book_ambiguous"
    elif res.chapter_id and res.book_slug in by and res.chapter_id not in by[res.book_slug].chapters:
        reason = "chapter_missing"
    if not reason:
        return None
    msg = {
        "book_unknown": "I couldn't match that to a book I have. Pick one of these:",
        "book_ambiguous": "I'm not sure which book you mean. Did you mean one of these?",
        "chapter_missing": "That book doesn't have that chapter. Pick a chapter:",
    }[reason]
    fallback_slugs = cand_slugs or [c.slug for c in catalog]
    cands = _candidate_records(fallback_slugs, catalog)[:6]
    return {
        "type": "clarify", "reason": reason, "message": msg,
        "candidates": cands, "chapter_guess": res.chapter_id,
        "sections_guess": res.requested_subtopics,
    }
