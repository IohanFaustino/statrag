"""Facilitate story mode — single-section narrative pipeline.

Pure-code binders/fidelity here; the LLM runner (run_facilitate_story) is
appended below. Chinese-wall: imports only src.core.* and sibling
src.services.chat.*.
"""
from __future__ import annotations

import re

from src.services.chat.schemas.output import ConceptAnchor  # noqa: E402 (used by helpers below)

_MARKER = re.compile(r"\[\[(c\d+)\]\]")


def referenced_ids(text: str) -> set[str]:
    return set(_MARKER.findall(text or ""))


def strip_unbound_markers(text: str, *, valid_ids: set[str]) -> str:
    """Remove [[cN]] markers whose id is not in valid_ids; keep surrounding text."""
    def repl(m: re.Match) -> str:
        return m.group(0) if m.group(1) in valid_ids else ""
    return _MARKER.sub(repl, text or "")


def bind_concepts(anchors: list[ConceptAnchor], *, referenced_ids: set[str]) -> list[ConceptAnchor]:
    """Keep only anchors actually referenced by a surviving [[cN]] marker."""
    return [a for a in anchors if a.id in referenced_ids]


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\$+", " ", s)             # drop math delimiters
    s = re.sub(r"[^a-z0-9\\ ]+", " ", s)   # keep latex backslash words + alnum
    return re.sub(r"\s+", " ", s).strip()


def statement_fidelity(statement: str, source_text: str) -> tuple[bool, float]:
    """Fuzzy token-recall of the formal statement against the source section.
    True when most statement tokens appear in the source (verbatim/near-verbatim)."""
    st = set(_norm(statement).split())
    src = set(_norm(source_text).split())
    if len(st) < 4:        # too short to be a credible formal statement
        return False, 0.0
    recall = len(st & src) / len(st)
    return recall >= 0.6, recall


# ---------------------------------------------------------------------------
# LLM runner — run_facilitate_story (single-section narrative pipeline)
# ---------------------------------------------------------------------------

import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from typing import AsyncIterator  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.services.chat._fences import strip_fences  # noqa: E402
from src.services.chat.agents._scope import (  # noqa: E402
    resolve_book,
    resolve_section,
    section_clarify,
    maybe_clarify,
)
from src.services.chat.books import parse_catalog  # noqa: E402
from src.services.chat.llm.router import aclient_for  # noqa: E402
from src.services.chat.llm.structured import apply_structured_output  # noqa: E402
from src.services.chat.prompts.chapter import (  # noqa: E402
    FACILITATE_STORY_WRITE_PROMPT,
    FACILITATE_MAP_PROMPT,
)
from src.services.chat.retrieval import fetch_chapter_sections  # noqa: E402
from src.services.chat.schemas import ChapterScope, ConceptProvenance, Source  # noqa: E402
from src.services.chat.schemas.output import (  # noqa: E402
    FacilitateStory,
    FacilitateStoryDraft,
    FormalStatement,
    Movement,
    FacilitateMap,
    StoryCitation,
)

logger = logging.getLogger(__name__)
_MAX_CONCEPTS = int(os.environ.get("FACILITATE_MAX_CONCEPTS", "5"))
_PREVIEW = 1500


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    oa = aclient_for(model)
    messages, response_format = apply_structured_output(messages, model, schema)
    kwargs = {"model": model, "messages": messages, "temperature": temperature,
              "max_completion_tokens": max_tokens}
    if response_format is not None:
        kwargs["response_format"] = response_format
    resp = await oa.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _model_for(stage: str, req) -> str:
    sm = getattr(req, "stageModels", None)
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    return settings.openai_model_nano


def _resolve_one_section(req):
    """Test seam — monkeypatched in tests. In prod the runner uses its inline
    async resolution path (this raises to signal 'use the inline path')."""
    raise NotImplementedError


async def _map(s: Source, *, model: str):
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_MAP_PROMPT},
                           {"role": "user", "content": user}], model=model, max_tokens=500, schema=FacilitateMap)
        data = json.loads(strip_fences(raw))
        concepts = []
        for c in (data.get("concepts") or [])[:_MAX_CONCEPTS]:
            term = str(c.get("term", "")).strip()
            if term:
                kind = c.get("kind") if c.get("kind") in ("concept", "theorem", "formula") else "concept"
                concepts.append({"term": term, "kind": kind, "status": c.get("status", "explained")})
        return [str(x) for x in (data.get("key_points") or [])], concepts
    except Exception:  # noqa: BLE001
        logger.exception("facilitate_story._map failed")
        return [], []


def _anchor_from_source(cid: str, c: dict, s: Source) -> ConceptAnchor:
    return ConceptAnchor(id=cid, term=c["term"], kind=c["kind"], explanation="",
        provenance=ConceptProvenance(
            book_slug=s.book, book_name=s.book_name or s.book, authors_short=s.authors_short or "",
            section=s.title, page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1, chunk_id=s.chunkId))


def _parse_draft(raw: str) -> FacilitateStoryDraft:
    try:
        data = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        logger.warning("facilitate_story._parse_draft: truncated/invalid JSON — returning empty draft")
        return FacilitateStoryDraft()
    movements = []
    for m in (data.get("movements") or []):
        f = m.get("formal")
        if isinstance(f, dict) and (f.get("statement") or "").strip():
            movements.append(Movement(formal=FormalStatement(
                kind=f.get("kind", "remark"), statement=f.get("statement", ""),
                explanation=f.get("explanation", ""))))
        elif (m.get("prose") or "").strip():
            movements.append(Movement(prose=m["prose"]))
    return FacilitateStoryDraft(hook=data.get("hook", ""), takeaway=data.get("takeaway", ""),
                                movements=movements, math_blocks=data.get("math_blocks") or [])


async def run_facilitate_story(req) -> AsyncIterator[dict]:
    t0 = time.time()
    message = req.message or ""
    bf = getattr(req, "bookFilter", None)
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {"type": "meta", "mode": "facilitate", "books": book_slugs or [],
           "sourceCount": 0, "latencyMs": 0, "model": getattr(req, "model", "nano")}
    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}

    try:
        scope, src, clarify = _resolve_one_section(req)
    except NotImplementedError:
        catalog = parse_catalog()
        res = await resolve_book(message, selected_slugs=book_slugs, catalog=catalog, model=_model_for("parse", req))
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar
            yield {"type": "done"}
            return
        sections = (
            fetch_chapter_sections(res.book_slug, res.chapter_id, max_sections=30)
            if res.book_slug and res.chapter_id
            else []
        )
        headings = [{"section_id": s.chunkId, "h2_path": s.title} for s in sections]
        sid, _score = resolve_section(message, subtopics=res.requested_subtopics, headings=headings)
        if not sid:
            if not headings:
                # No sections fetched — book/chapter didn't resolve to anything teachable.
                # Emit a book/chapter clarify instead of an empty section list.
                clar = maybe_clarify(res, catalog)
                if clar is not None:
                    yield clar
                else:
                    yield {
                        "type": "clarify",
                        "reason": "chapter_empty",
                        "message": (
                            "I couldn't load any sections for that chapter. "
                            "Try naming the chapter explicitly (e.g. 'chapter 7') or pick a book."
                        ),
                        "candidates": [],
                        "chapter_guess": res.chapter_id,
                    }
            else:
                yield section_clarify(headings=headings, chapter_id=res.chapter_id)
            yield {"type": "done"}
            return
        src = next((s for s in sections if s.chunkId == sid), None)
        scope = ChapterScope(book_slug=res.book_slug, chapter_id=res.chapter_id,
                             requested_subtopics=res.requested_subtopics, section_id=sid)
        clarify = None
    if clarify is not None:
        yield clarify
        yield {"type": "done"}
        return
    if src is None:
        yield section_clarify(headings=[], chapter_id=getattr(scope, "chapter_id", ""))
        yield {"type": "done"}
        return

    yield {"type": "stage", "stage": "map", "label": f"Map · {src.title}"}
    _kps, concept_dicts = await _map(src, model=_model_for("map", req))
    anchors = [_anchor_from_source(f"c{i}", c, src) for i, c in enumerate(concept_dicts, 1)]

    yield {"type": "stage", "stage": "write", "label": "Write story"}
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {src.title}\nconcept ids: {ids}\n\nsection text:\n"
            f"{(src.chunk or src.excerpt or '')[:_PREVIEW]}")
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_STORY_WRITE_PROMPT},
                           {"role": "user", "content": user}],
                          model=_model_for("write", req), max_tokens=2600, schema=FacilitateStoryDraft)
        draft = _parse_draft(raw)
    except Exception:  # noqa: BLE001
        logger.exception("facilitate_story.write failed")
        draft = FacilitateStoryDraft(hook="", takeaway="", movements=[Movement(prose=src.excerpt or src.title)])

    valid = {a.id for a in anchors}
    used: set[str] = set()
    new_movs = []
    for m in draft.movements:
        if m.prose:
            txt = strip_unbound_markers(m.prose, valid_ids=valid)
            used |= referenced_ids(txt)
            new_movs.append(Movement(prose=txt))
        elif m.formal:
            expl = strip_unbound_markers(m.formal.explanation, valid_ids=valid)
            used |= referenced_ids(expl)
            new_movs.append(Movement(formal=FormalStatement(
                kind=m.formal.kind, statement=m.formal.statement, explanation=expl)))
    bound = bind_concepts(anchors, referenced_ids=used)

    yield {"type": "stage", "stage": "verify", "label": "Verify"}
    grounding = {"ok": True, "unsupported": [], "confidence": 1.0}
    for m in new_movs:
        if m.formal:
            ok, _sc = statement_fidelity(m.formal.statement, src.chunk or src.excerpt or "")
            if not ok:
                grounding = {"ok": False, "unsupported": [m.formal.statement[:120]], "confidence": 0.4}

    citations = [StoryCitation(kind="corpus",
        label=f"{src.authors_short or src.book} §{src.title}",
        book_slug=src.book, book_name=src.book_name, authors=src.authors_short,
        chapter=src.chapter, section_id=src.section,
        pages=(f"{src.page_from}–{src.page_to}" if src.page_from else None),
        chunk_id=src.chunkId)]

    story = FacilitateStory(mode="facilitate_story", scope=scope, hook=draft.hook,
        movements=new_movs, takeaway=draft.takeaway, concepts=bound,
        citations=citations, math_blocks=draft.math_blocks, grounding=grounding)
    yield {"type": "structured_output", "schema": "FacilitateStory", "data": story.model_dump()}
    yield {"type": "sources_full", "sources": [src.model_dump()]}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000),
           "promptChars": len(message), "completionChars": len(draft.hook), "estTokens": 0}
    yield {"type": "done"}
