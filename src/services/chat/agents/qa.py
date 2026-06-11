"""Punctual Q&A mode agent.

Four-node pipeline: scope -> retrieve -> scoped generate -> verify/finalise.
Each LLM node goes through the single ``_chat`` seam so tests can monkeypatch
one function. Reuses ``retrieval.hybrid_search``. Emits the v1 SSE event schema.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import AsyncIterator

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents._scope import maybe_clarify, resolve_book
from src.services.chat.books import parse_catalog
from src.services.chat.llm.router import aclient_for
from src.services.chat.llm.structured import apply_structured_output
from src.services.chat.prompts.qa import (
    QA_GENERATE_PROMPT,
    QA_SCOPE_PROMPT,
    QA_VERIFY_PROMPT,
)
from src.services.chat.research import (
    Evidence, _citation, _isolate_midline_display, corpus_evidence, wiki_evidence,
)
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas import (
    ChatRequest, QAAnswer, QAGenerateOut, QAScope, QAStoryAnswer, QAStoryDraft,
    QAVerifyOut, Source, TutorCitation,
)

logger = logging.getLogger(__name__)

_QA_TOP_K = int(os.environ.get("QA_TOP_K", "4"))
_QA_SCOPE = os.environ.get("QA_SCOPE", "1") == "1"
_QA_VERIFY = os.environ.get("QA_VERIFY", "1") == "1"
_QA_CLARIFY = os.environ.get("CHAPTER_CLARIFY", "1") == "1"
_QA_WIKI = os.environ.get("QA_WIKI", "1") == "1"
_QA_WIKI_TERMS_MAX = int(os.environ.get("QA_WIKI_TERMS_MAX", "2"))

# m1: module constant for chunk preview truncation
_CHUNK_PREVIEW_CHARS = 1500


def _model_for(stage: str, req: ChatRequest | None) -> str:
    """Resolve the model for a Q&A stage: stageModels override > env > nano."""
    # I1: direct attribute access — ChatRequest always has stageModels
    sm = req.stageModels if req else None
    if sm and isinstance(sm.get(stage), str) and sm[stage].strip():
        return sm[stage].strip()
    env = os.environ.get(f"QA_{stage.upper()}_MODEL", "").strip()
    return env or settings.openai_model_nano


async def _chat(messages, *, model, max_tokens, temperature=0.0, schema=None) -> str:
    """Single LLM seam. Returns the raw assistant content string.

    Routes through the per-model structured-output gate: json_schema when the
    model supports it, else json_object + a <response_format> hint appended to
    the system message. Parsing stays defensive downstream (strip_fences +
    json.loads), so json_object-only providers are still handled.
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


async def extract_scope(query: str, *, model: str | None = None) -> QAScope:
    """Parse the query into {target_gap, assumed_known, answer_form}.

    Fail-open: on any error the whole query becomes the gap with nothing
    assumed known.
    """
    fallback = QAScope(target_gap=query.strip(), assumed_known=[], answer_form="explanation")
    if not query.strip():
        return fallback
    chosen = model or settings.openai_model_nano
    try:
        raw = await _chat(
            [
                {"role": "system", "content": QA_SCOPE_PROMPT},
                {"role": "user", "content": query},
            ],
            model=chosen,
            max_tokens=200,
            schema=QAScope,
        )
        data = json.loads(strip_fences(raw))
        return QAScope(
            target_gap=str(data.get("target_gap") or query).strip(),
            assumed_known=[str(x).strip() for x in (data.get("assumed_known") or []) if str(x).strip()],
            answer_form=data.get("answer_form") if data.get("answer_form") in {
                "explanation", "definition", "comparison", "derivation", "yes_no", "list"
            } else "explanation",
        )
    except Exception:  # noqa: BLE001
        logger.exception("qa.extract_scope failed; using fail-open scope")
        return fallback


def retrieve_for_gap(
    scope: QAScope,
    *,
    book_slugs: list[str] | None,
    k: int = _QA_TOP_K,
) -> tuple[list[Source], dict]:
    """Hybrid-retrieve using the narrowed ``target_gap`` (sharper than the raw
    query). Narrow ``k`` for precision; reranking on.

    When rerank=True the final count is governed by ``rerank_top_n`` (not
    ``top_k``).  We pass both so the reranker actually limits output to ``k``.
    """
    sources, meta = hybrid_search(
        scope.target_gap,
        book_slugs=book_slugs,
        top_k=max(1, int(k)),
        rerank=True,
        rerank_top_n=max(1, int(k)),
        adjacent_sections=False,
    )
    return sources, meta


def _sources_block(sources: list[Source]) -> str:
    """Render numbered sources for the generate/verify prompts."""
    lines = []
    # m2: contiguous 1-based citation labels via enumerate(sources, 1)
    for i, s in enumerate(sources, 1):
        body = (s.chunk or s.excerpt or "")[:_CHUNK_PREVIEW_CHARS]
        lines.append(
            f"[{i}] {s.book_name or s.book} · {s.chapter} {s.section} — "
            f"{s.title}\n{body}"
        )
    return "\n\n".join(lines)


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


async def generate_scoped(
    scope: QAScope,
    sources: list[Source],
    *,
    model: str | None = None,
) -> QAAnswer:
    """Generate a terse, scoped answer. One schema-repair retry (ADR-005)."""
    chosen = model or settings.openai_model_nano
    user = (
        f"target_gap: {scope.target_gap}\n"
        f"assumed_known: {json.dumps(scope.assumed_known)}\n"
        f"answer_form: {scope.answer_form}\n\n"
        f"sources:\n{_sources_block(sources)}"
    )
    messages = [
        {"role": "system", "content": QA_GENERATE_PROMPT},
        {"role": "user", "content": user},
    ]

    async def _one() -> dict:
        raw = await _chat(messages, model=chosen, max_tokens=900, schema=QAGenerateOut)
        return json.loads(strip_fences(raw))

    try:
        data = await _one()
    except (json.JSONDecodeError, ValueError):  # C2: narrow to parse failures only
        logger.warning("qa.generate_scoped first parse failed; repair retry")
        data = await _one()

    return QAAnswer(
        text=str(data.get("text", "")).strip(),
        scope=scope,
        citations=_coerce_citations(data.get("citations")),
        math_blocks=[str(m) for m in (data.get("math_blocks") or []) if str(m).strip()],
        grounding={},
    )


async def verify_grounding(
    answer: QAAnswer,
    sources: list[Source],
    *,
    model: str | None = None,
) -> QAAnswer:
    """Audit the draft against sources. Advisory: fail-open keeps the draft and
    marks low confidence; it never suppresses the answer."""
    chosen = model or settings.openai_model_nano
    user = (
        f"draft text:\n{answer.text}\n\nsources:\n{_sources_block(sources)}"
    )
    try:
        raw = await _chat(
            [
                {"role": "system", "content": QA_VERIFY_PROMPT},
                {"role": "user", "content": user},
            ],
            model=chosen,
            max_tokens=700,
            schema=QAVerifyOut,
        )
        data = json.loads(strip_fences(raw))
        verified_text = str(data.get("text") or answer.text).strip()
        grounding = {
            "ok": bool(data.get("ok", False)),
            "unsupported": [str(x) for x in (data.get("unsupported") or [])],
            "confidence": float(data.get("confidence", 0.5)),
        }
        return answer.model_copy(update={"text": verified_text, "grounding": grounding})
    except Exception:  # noqa: BLE001
        logger.exception("qa.verify_grounding failed; keeping draft, low confidence")
        return answer.model_copy(update={
            "grounding": {"ok": False, "unsupported": [], "confidence": 0.5}
        })


async def retrieve_evidence(
    scope: QAScope,
    *,
    book_slugs: list[str] | None,
) -> list[Evidence]:
    """Gather corpus + Wikipedia evidence in a single asyncio.gather.

    Always calls corpus_evidence once for scope.target_gap.  When _QA_WIKI
    is True, additionally calls wiki_evidence once for target_gap and once
    per wiki_terms entry (capped at _QA_WIKI_TERMS_MAX).

    Returns a flat list[Evidence]; each Evidence already carries a unique .id
    from its factory default.
    """
    coro_corpus = asyncio.to_thread(
        corpus_evidence,
        scope.target_gap,
        subject_id="qa",
        exclude_book="",
        all_slugs=(book_slugs or []),
        seen_ids=set(),
        top_n=_QA_TOP_K,
    )

    wiki_queries: list[str] = []
    if _QA_WIKI:
        wiki_queries = [scope.target_gap, *scope.wiki_terms[:_QA_WIKI_TERMS_MAX]]

    wiki_coros = [
        asyncio.to_thread(wiki_evidence, q, subject_id="qa")
        for q in wiki_queries
    ]

    gathered = await asyncio.gather(coro_corpus, *wiki_coros, return_exceptions=True)

    result: list[Evidence] = []
    for i, batch in enumerate(gathered):
        if isinstance(batch, BaseException):
            label = "corpus" if i == 0 else f"wiki[{i - 1}]"
            logger.warning("retrieve_evidence: %s fetch raised %s: %s",
                           label, type(batch).__name__, batch)
            continue
        result.extend(batch)
    return result


# ---------------------------------------------------------------------------
# Paragraph cap constants (intro≤1, deepening≤3, conclusion≤1)
# ---------------------------------------------------------------------------
_PARA_CAPS: dict[str, int] = {"intro": 1, "deepening": 3, "conclusion": 1}


def _strip_heading_markers(text: str) -> str:
    """Remove leading #{1,6} from every line so markdown headings become plain text."""
    return "\n".join(re.sub(r'^#{1,6}\s*', '', line) for line in text.splitlines())


def _apply_token_pass(
    fields: dict[str, str],
    by_id: dict[str, Evidence],
) -> tuple[dict[str, str], list, int]:
    """Scan intro→deepening→conclusion for [[eid]] tokens.

    Returns (rewritten_fields, citations, unbound_count).
    """
    from src.services.chat.schemas.output import StoryCitation  # local import avoids circular

    seen: dict[str, int] = {}     # eid → citation number (1-based)
    citations: list[StoryCitation] = []
    unbound = 0

    def _replace(text: str) -> str:
        nonlocal unbound

        def _sub(m: re.Match) -> str:
            nonlocal unbound
            eid = m.group(1)
            if eid not in by_id:
                unbound += 1
                return ""
            if eid not in seen:
                n = len(seen) + 1
                seen[eid] = n
                citations.append(_citation(by_id[eid]))
            return f"[{seen[eid]}]"

        result = re.sub(r'\[\[([^\]]+)\]\]', _sub, text)
        # Collapse any doubled spaces left by removed tokens
        result = re.sub(r'  +', ' ', result)
        # Remove orphan space before punctuation (e.g. "holds ." → "holds.")
        result = re.sub(r'\s+([.,;:!?])', r'\1', result)
        return result

    rewritten = {field: _replace(text) for field, text in fields.items()}
    return rewritten, citations, unbound


def qa_bind(
    draft: QAStoryDraft,
    evidence: list[Evidence],
    *,
    scope: QAScope | None = None,
) -> QAStoryAnswer:
    """Pure-code citation binder.

    1. Strip markdown heading markers from all three fields.
    2. Apply [[eid]] → [n] substitution with shared first-appearance counter;
       invalid eids are removed (prose kept), counted in grounding['unbound_markers'].
    3. Enforce paragraph caps (intro≤1, deepening≤3, conclusion≤1); excess
       paragraphs are dropped and the field name is recorded in grounding['lints'].
    4. Apply mid-line $$...$$ → $...$ normalization via _isolate_midline_display.
    """
    by_id: dict[str, Evidence] = {e.id: e for e in evidence}

    # Step 1 — strip heading markers
    stripped = {
        "intro": _strip_heading_markers(draft.intro),
        "deepening": _strip_heading_markers(draft.deepening),
        "conclusion": _strip_heading_markers(draft.conclusion),
    }

    # Step 2 — token pass (order: intro → deepening → conclusion)
    field_order = ["intro", "deepening", "conclusion"]
    ordered = {f: stripped[f] for f in field_order}
    rewritten, citations, unbound = _apply_token_pass(ordered, by_id)

    # Step 3 — paragraph caps
    lints: list[str] = []
    for field, cap in _PARA_CAPS.items():
        paragraphs = re.split(r'\n\n+', rewritten[field])
        non_empty = [p for p in paragraphs if p.strip()]
        if len(non_empty) > cap:
            lints.append(f"{field}: truncated from {len(non_empty)} to {cap} paragraphs")
            rewritten[field] = "\n\n".join(non_empty[:cap])

    # Step 4 — mid-line display math normalisation
    for field in field_order:
        rewritten[field] = _isolate_midline_display(rewritten[field])

    # Build scope placeholder when not provided
    effective_scope = scope if scope is not None else QAScope(target_gap="")

    return QAStoryAnswer(
        intro=rewritten["intro"],
        deepening=rewritten["deepening"],
        conclusion=rewritten["conclusion"],
        scope=effective_scope,
        citations=citations,
        math_blocks=draft.math_blocks,
        grounding={"unbound_markers": unbound, "lints": lints},
    )


async def run_qa(req: ChatRequest) -> AsyncIterator[dict]:
    """Execute the punctual Q&A pipeline and yield v1 SSE event dicts."""
    t0 = time.time()
    query = req.message or ""
    # I1: direct attribute access — ChatRequest always has bookFilter
    bf = req.bookFilter
    book_slugs = list(bf) if isinstance(bf, list) and bf else None

    yield {
        "type": "meta",
        "mode": "qa",
        "books": book_slugs or [],
        "sourceCount": 0,
        "latencyMs": int((time.time() - t0) * 1000),
        "model": req.model,
    }

    # 0b. resolve book scope from the question (fuzzy) + confirm gate
    catalog = parse_catalog()
    res = await resolve_book(query, selected_slugs=book_slugs or [], catalog=catalog,
                             model=_model_for("scope", req))
    if _QA_CLARIFY:
        clar = maybe_clarify(res, catalog)
        if clar is not None:
            yield clar
            yield {"type": "done"}
            return
    if res.book_slug:
        book_slugs = [res.book_slug]

    # 1. scope
    scope = (
        await extract_scope(query, model=_model_for("scope", req))
        if _QA_SCOPE
        else QAScope(target_gap=query.strip())
    )

    # 2. retrieve on the gap
    sources, retr_meta = retrieve_for_gap(scope, book_slugs=book_slugs, k=_QA_TOP_K)

    # 2b. corpus miss → honest answer, no fabricated citation
    if not sources:
        answer = QAAnswer(
            text=("That topic is not covered in the selected books. Try widening the "
                  "book filter or rephrasing."),
            scope=scope,
            citations=[],
            grounding={"ok": True, "unsupported": [], "confidence": 1.0},
        )
        yield {"type": "structured_output", "schema": "QAAnswer", "data": answer.model_dump()}
        yield {"type": "sources_full", "sources": []}
        # I3: emit retrieval_meta and usage on corpus-miss path too
        yield {
            "type": "retrieval_meta",
            "meta": {
                "rewrittenQuery": scope.target_gap[:300],
                "embedding": settings.embedding_model,
                "retrievalMs": int((time.time() - t0) * 1000),
                "collections": retr_meta.get("collections", []) if isinstance(retr_meta, dict) else [],
                "filter": "qa",
                "topK": _QA_TOP_K,
                "scoreThreshold": 0.0,
                "mode": "qa (scope→retrieve→generate→verify)",
            },
        }
        yield {
            "type": "usage",
            "durationMs": int((time.time() - t0) * 1000),
            "promptChars": len(query),
            "completionChars": len(answer.text),
            "estTokens": (len(query) + len(answer.text)) // 4,
        }
        yield {"type": "done"}
        return

    # C2: guard generate + verify calls so SSE stream always terminates cleanly
    try:
        # 3. scoped generate
        answer = await generate_scoped(scope, sources, model=_model_for("generate", req))

        # 4. verify / finalise (advisory)
        if _QA_VERIFY:
            answer = await verify_grounding(answer, sources, model=_model_for("verify", req))
        elif not answer.grounding:
            answer = answer.model_copy(update={"grounding": {"ok": True, "unsupported": [], "confidence": 0.7}})
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "code": type(exc).__name__, "message": str(exc)}
        yield {"type": "done"}
        return

    yield {"type": "structured_output", "schema": "QAAnswer", "data": answer.model_dump()}
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
            for s in sources
        ],
    }
    yield {
        "type": "retrieval_meta",
        "meta": {
            "rewrittenQuery": scope.target_gap[:300],
            "embedding": settings.embedding_model,
            "retrievalMs": int((time.time() - t0) * 1000),
            "collections": retr_meta.get("collections", []) if isinstance(retr_meta, dict) else [],
            "filter": "qa",
            "topK": _QA_TOP_K,
            "scoreThreshold": 0.0,
            "mode": "qa (scope→retrieve→generate→verify)",
        },
    }
    yield {
        "type": "usage",
        "durationMs": int((time.time() - t0) * 1000),
        "promptChars": len(query),
        "completionChars": len(answer.text),
        "estTokens": (len(query) + len(answer.text)) // 4,
    }
    yield {"type": "done"}
