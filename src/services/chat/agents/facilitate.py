"""Facilitate mode: concept-map-first teaching pipeline.

Per section, in order: build a concept map (key points + concepts), sub-retrieve
explanations for referenced concepts (same-author-first), rewrite the section as
short/clear key points with [[cN]] anchors, then verify grounding. Emits the v1
SSE schema with structured_output schema "FacilitateDigest".

Chinese-wall: imports only src.core.* and sibling src.services.chat.*.
"""
from __future__ import annotations

import asyncio
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
from src.services.chat.schemas.output import FacilitateMap, FacilitateVerify
from src.services.chat.prompts.chapter import (
    FACILITATE_EXPLAIN_PROMPT,
    FACILITATE_INTRO_PROMPT,
    FACILITATE_MAP_PROMPT,
    FACILITATE_TEACH_PROMPT,
    FACILITATE_VERIFY_PROMPT,
)
from src.services.chat.retrieval import (
    _section_order_in_book,
    fetch_chapter_sections,
    fetch_concept_support,
)
from src.services.chat.schemas import (
    ChapterScope,
    ConceptAnchor,
    ConceptProvenance,
    FacilitateBlock,
    FacilitateDigest,
    Source,
)

logger = logging.getLogger(__name__)

_MAX_SECTIONS = int(os.environ.get("CHAPTER_MAX_SECTIONS", "30"))
_MAX_CONCEPTS = int(os.environ.get("FACILITATE_MAX_CONCEPTS", "5"))
_MAX_KEYPOINTS = int(os.environ.get("FACILITATE_MAX_KEYPOINTS", "6"))
_MIN_SCORE = float(os.environ.get("CONCEPT_MIN_SCORE", "0.30"))
_SUBRETRIEVAL = os.environ.get("FACILITATE_SUBRETRIEVAL", "1") == "1"
_CLARIFY = os.environ.get("CHAPTER_CLARIFY", "1") == "1"
_GROUND = os.environ.get("CHAPTER_GROUND", "1") == "1"
_PREVIEW = 1500


def _model_for(stage: str, req) -> str:
    sm = req.stageModels if req else None
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    env = os.environ.get(f"FACILITATE_{stage.upper()}_MODEL", "").strip()
    if env:
        return env
    return "qwen-plus" if stage == "teach" else settings.openai_model_nano


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
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


async def _map_section(s: Source, *, model: str) -> tuple[list[str], list[dict]]:
    user = f"heading: {s.title}\n\nsection text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}"
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_MAP_PROMPT},
                           {"role": "user", "content": user}], model=model, max_tokens=500,
                          schema=FacilitateMap)
        data = json.loads(strip_fences(raw))
        kps = [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()][:_MAX_KEYPOINTS]
        concepts = []
        for c in (data.get("concepts") or [])[:_MAX_CONCEPTS]:
            term = str(c.get("term", "")).strip()
            if not term:
                continue
            kind = c.get("kind") if c.get("kind") in ("concept", "theorem", "formula") else "concept"
            status = "referenced" if c.get("status") == "referenced" else "explained"
            concepts.append({"term": term, "kind": kind, "status": status})
        return kps, concepts
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._map_section failed at %s", s.chunkId)
        excerpt = (s.excerpt or "")[:200]
        return ([excerpt] if excerpt else []), []


async def _explain(term: str, passage: str, *, model: str) -> str:
    try:
        out = await _chat([{"role": "system", "content": FACILITATE_EXPLAIN_PROMPT},
                           {"role": "user", "content": f"term: {term}\n\npassage:\n{passage[:_PREVIEW]}"}],
                          model=model, max_tokens=200)
        return out.strip()
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._explain failed for %s", term)
        return passage[:200]


async def _build_one_concept(s: Source, c: dict, cid: str, *, order: dict, explain_model: str) -> ConceptAnchor:
    """Build one ConceptAnchor, threading out the synchronous retrieval call."""
    term, kind, status = c["term"], c["kind"], c["status"]
    if status == "referenced" and _SUBRETRIEVAL:
        sup = await asyncio.to_thread(
            fetch_concept_support, term, book_slug=s.book,
            before_section_id=s.chunkId, min_score=_MIN_SCORE, order=order)
        if sup is not None:
            expl = await _explain(term, sup.text, model=explain_model)
            return ConceptAnchor(id=cid, term=term, kind=kind, explanation=expl,
                provenance=ConceptProvenance(book_slug=sup.book_slug, book_name=sup.book_name,
                    authors_short=sup.authors_short, section=sup.section, page_from=sup.page_from,
                    page_to=sup.page_to, chunk_id=sup.chunk_id, same_author=sup.same_author, fallback=False))
    expl = await _explain(term, (s.chunk or s.excerpt or ""), model=explain_model)
    return ConceptAnchor(id=cid, term=term, kind=kind, explanation=expl,
        provenance=ConceptProvenance(book_slug=s.book, book_name=s.book_name or s.book,
            authors_short=s.authors_short or "", section=s.title,
            page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1, chunk_id=s.chunkId,
            same_author=(status != "referenced"), fallback=(status == "referenced")))


async def _build_concepts(s: Source, concept_dicts: list[dict], *, explain_model: str) -> list[ConceptAnchor]:
    """Build all ConceptAnchors for a section (kept for eval compatibility)."""
    order = await asyncio.to_thread(_section_order_in_book, s.book) if s.book else {}
    anchors: list[ConceptAnchor] = []
    for i, c in enumerate(concept_dicts, 1):
        anchors.append(await _build_one_concept(s, c, f"c{i}", order=order, explain_model=explain_model))
    return anchors


async def _teach(s: Source, key_points: list[str], anchors: list[ConceptAnchor], *, model: str) -> str:
    ids = "; ".join(f"{a.id}={a.term}" for a in anchors)
    user = (f"heading: {s.title}\nconcept ids: {ids}\nkey points: {key_points}\n\n"
            f"section text:\n{(s.chunk or s.excerpt or '')[:_PREVIEW]}")
    try:
        body = await _chat([{"role": "system", "content": FACILITATE_TEACH_PROMPT},
                            {"role": "user", "content": user}], model=model, max_tokens=700)
        return body.strip() or "\n".join(f"- {k}" for k in key_points)
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._teach failed at %s", s.chunkId)
        return "\n".join(f"- {k}" for k in key_points)


async def _verify(body: str, section_text: str, *, model: str) -> tuple[str, dict]:
    """Proofread/repair the body and judge grounding. Returns (fixed_body, grounding).

    Fail-open: on any error keep the original body and a neutral grounding.
    """
    try:
        raw = await _chat([{"role": "system", "content": FACILITATE_VERIFY_PROMPT},
                           {"role": "user", "content": f"SOURCE:\n{section_text[:_PREVIEW]}\n\nBODY:\n{body}"}],
                          model=model, max_tokens=1100, schema=FacilitateVerify)
        d = json.loads(strip_fences(raw))
        fixed = str(d.get("fixed_body") or "").strip() or body
        grounding = {"ok": bool(d.get("ok", False)),
                     "unsupported": [str(x) for x in (d.get("unsupported") or [])],
                     "confidence": float(d.get("confidence", 0.5))}
        return fixed, grounding
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._verify failed; keeping original body")
        return body, {"ok": False, "unsupported": [], "confidence": 0.5}


async def _intro(scope, sections, *, model: str) -> str:
    headings = "; ".join(s.title for s in sections)
    user = f"chapter: {scope.chapter_id}\nsections (in order): {headings}"
    try:
        out = await _chat([{"role": "system", "content": FACILITATE_INTRO_PROMPT},
                           {"role": "user", "content": user}], model=model, max_tokens=120)
        return out.strip()
    except Exception:  # noqa: BLE001
        logger.exception("facilitate._intro failed")
        return ""


async def run_facilitate(req) -> AsyncIterator[dict]:
    t0 = time.time()
    message = req.message or ""
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {"type": "meta", "mode": "facilitate", "books": book_slugs or [],
           "sourceCount": 0, "latencyMs": 0, "model": req.model}

    yield {"type": "stage", "stage": "parse", "label": "Parse + resolve scope"}
    catalog = parse_catalog()
    res = await resolve_book(message, selected_slugs=book_slugs, catalog=catalog, model=_model_for("map", req))
    scope = ChapterScope(book_slug=res.book_slug, chapter_id=res.chapter_id, requested_subtopics=res.requested_subtopics)
    if _CLARIFY:
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar
            yield {"type": "done"}
            return

    yield {"type": "stage", "stage": "fetch", "label": "Fetch chapter"}
    try:
        sections = fetch_chapter_sections(scope.book_slug, scope.chapter_id, max_sections=_MAX_SECTIONS) \
            if scope.book_slug and scope.chapter_id else []
    except Exception:  # noqa: BLE001
        logger.exception("facilitate.run_facilitate: fetch failed")
        sections = []
    if scope.requested_subtopics:
        wanted = [t.lower() for t in scope.requested_subtopics]
        filt = [s for s in sections if any(w in s.title.lower() for w in wanted)]
        sections = filt or sections

    if not sections:
        dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=[],
            intro="Chapter not found in the selected books. Pick a book and name a chapter (e.g. 'ch02').",
            grounding={"ok": True, "unsupported": [], "confidence": 1.0})
        yield {"type": "structured_output", "schema": "FacilitateDigest", "data": dig.model_dump()}
        yield {"type": "sources_full", "sources": []}
        yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000), "promptChars": len(message),
               "completionChars": len(dig.intro), "estTokens": 0}
        yield {"type": "done"}
        return

    # Build section order once per request to avoid re-scrolling on each concept (FIX 6).
    order = await asyncio.to_thread(_section_order_in_book, scope.book_slug) if scope.book_slug else {}

    blocks: list[FacilitateBlock] = []
    groundings: list[dict] = []
    for s in sections:
        yield {"type": "stage", "stage": "map", "label": f"Map · {s.title}"}
        key_points, concept_dicts = await _map_section(s, model=_model_for("map", req))
        anchors: list[ConceptAnchor] = []
        for i, c in enumerate(concept_dicts, 1):
            cid = f"c{i}"
            # Yield retrieve event immediately before the actual retrieval (FIX 2).
            if c["status"] == "referenced" and _SUBRETRIEVAL:
                yield {"type": "stage", "stage": "retrieve", "label": f"Retrieve · {c['term']}"}
            anchors.append(await _build_one_concept(s, c, cid, order=order,
                                                    explain_model=_model_for("explain", req)))
        yield {"type": "stage", "stage": "teach", "label": f"Teach · {s.title}"}
        body = await _teach(s, key_points, anchors, model=_model_for("teach", req))
        yield {"type": "stage", "stage": "verify", "label": f"Verify · {s.title}"}
        body, grounding_i = await _verify(body, (s.chunk or s.excerpt or ""), model=_model_for("verify", req))
        groundings.append(grounding_i)
        blocks.append(FacilitateBlock(
            h2_path=s.title, section_id=s.chunkId, key_points=key_points, body=body,
            concepts=anchors, page_from=s.page_from if s.page_from is not None else -1,
            page_to=s.page_to if s.page_to is not None else -1))

    yield {"type": "stage", "stage": "intro", "label": "Overview"}
    intro_text = await _intro(scope, sections, model=_model_for("map", req))

    grounding = {
        "ok": all(g.get("ok") for g in groundings) if groundings else True,
        "unsupported": [u for g in groundings for u in g.get("unsupported", [])],
        "confidence": (sum(g.get("confidence", 0.0) for g in groundings) / len(groundings)) if groundings else 1.0,
    }

    joined = "\n".join(b.body for b in blocks)
    dig = FacilitateDigest(mode="facilitate", scope=scope, blocks=blocks, intro=intro_text, grounding=grounding)
    yield {"type": "structured_output", "schema": "FacilitateDigest", "data": dig.model_dump()}
    yield {"type": "sources_full", "sources": [s.model_dump() for s in sections]}
    yield {"type": "usage", "durationMs": int((time.time() - t0) * 1000), "promptChars": len(message),
           "completionChars": len(joined), "estTokens": (len(message) + len(joined)) // 4}
    yield {"type": "done"}
