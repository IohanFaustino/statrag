"""LangGraph re-implementation of the ``research`` multi-agent graph (T11).

Per-claim retrieval + stance classification fan out via ``Send`` so up to N
claims run in parallel. Replaces the serial loop in v1 (one claim at a time,
8 LLM calls + 6 retrievals back-to-back).

Pipeline:

  extract_claims
      └─► (Send per claim) ─► retrieve_and_classify ─► merge
                                                       └─► synthesize
                                                              └─► END

``retrieve_and_classify`` is a single worker node that does both per-claim
retrieval and stance classification — keeping the LangGraph topology simple
while still parallel.

Chinese-wall: imports only ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import operator
from typing import Annotated, Any

import openai as _openai
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas.output import Citation, Report, StanceClaim

logger = logging.getLogger(__name__)


class _ResearchState(TypedDict, total=False):
    query: str
    book_slugs: list[str] | None
    claims_raw: list[str]
    classified: Annotated[list[dict], operator.add]
    synthesis: str
    coverage_gaps: list[str]


async def extract_claims(state: _ResearchState) -> dict:
    """Decompose the excerpt into 3-8 atomic claims (one nano LLM call)."""
    prompt = (
        "Decompose the following research excerpt into 3-8 atomic factual "
        "claims. Each claim is a single short standalone statement. Return "
        'ONLY JSON: {"claims": ["claim 1", ...]}\n\n'
        f"Excerpt:\n{state.get('query', '')[:4000]}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.1,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        data = json.loads(raw)
        claims = [c for c in data.get("claims", []) if isinstance(c, str) and c.strip()]
    except Exception:  # noqa: BLE001
        logger.exception("research_lg.extract_claims failed")
        claims = []
    return {"claims_raw": claims}


def fanout_claims(state: _ResearchState):
    """Route each claim to a parallel worker."""
    book_slugs = state.get("book_slugs")
    return [
        Send("classify_claim", {"claim": c, "book_slugs": book_slugs})
        for c in state.get("claims_raw", [])
    ]


async def classify_claim(payload: dict) -> dict:
    """Worker: hybrid retrieve top-3 + nano stance classification per evidence."""
    claim: str = payload["claim"]
    book_slugs: list[str] | None = payload.get("book_slugs")

    try:
        srcs, _ = await asyncio.to_thread(
            hybrid_search, claim, book_slugs=book_slugs, top_k=3, rerank=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_lg.classify_claim: retrieval failed: %s", exc)
        srcs = []

    evidence: list[dict] = [
        {
            "book": s.book, "chapter": s.chapter, "section": s.section,
            "chunk": (s.chunk or "")[:1500], "score": s.score,
        }
        for s in srcs[:3]
    ]
    if not evidence:
        return {"classified": [{
            "text": claim, "stance": "BACKGROUND", "confidence": 0.0, "evidence": [],
        }]}

    evidence_blocks = "\n\n".join(
        f"EVIDENCE {i + 1}:\n{ev['chunk'][:1200]}" for i, ev in enumerate(evidence)
    )
    prompt = (
        "Classify each EVIDENCE as SUPPORTS, CONTRADICTS, or BACKGROUND with "
        "respect to the CLAIM. Return ONLY JSON: "
        '{"results": [{"stance": "...", "confidence": 0.0-1.0}, ...]}\n\n'
        f"CLAIM: {claim}\n\n{evidence_blocks}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        results = json.loads(raw).get("results", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_lg.classify_claim: LLM failed: %s", exc)
        results = []

    stances = [r.get("stance", "BACKGROUND") for r in results]
    confs = [float(r.get("confidence", 0.0)) for r in results]
    non_bg = [(s, c) for s, c in zip(stances, confs) if s != "BACKGROUND"]
    if non_bg:
        stance, conf = max(non_bg, key=lambda x: x[1])
    elif confs:
        stance, conf = "BACKGROUND", max(confs)
    else:
        stance, conf = "BACKGROUND", 0.0

    sorted_ev = sorted(evidence, key=lambda x: -float(x.get("score", 0.0)))
    return {"classified": [{
        "text": claim,
        "stance": stance,
        "confidence": conf,
        "evidence": sorted_ev[:2],
    }]}


async def synthesize(state: _ResearchState) -> dict:
    """Write a 4-6 sentence synthesis paragraph + coverage_gaps list."""
    claims = state.get("classified", [])
    claims_summary = "\n".join(
        f"- [{c.get('stance', 'BACKGROUND')}, conf={c.get('confidence', 0.0):.2f}] {c['text']}"
        for c in claims
    )
    prompt = (
        "Below is a list of claims with their evidence stances from a textbook "
        "corpus. Write a 4-6 sentence synthesis paragraph describing how the "
        "corpus aligns with the excerpted research. Mention any claims with "
        "zero supporting evidence as coverage gaps. Return ONLY JSON: "
        '{"synthesis": "...", "coverage_gaps": ["claim text", ...]}\n\n'
        f"{claims_summary}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        j = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_lg.synthesize failed: %s", exc)
        j = {"synthesis": "", "coverage_gaps": []}

    return {
        "synthesis": j.get("synthesis", ""),
        "coverage_gaps": j.get("coverage_gaps", []),
    }


def _build_graph():
    g = StateGraph(_ResearchState)
    g.add_node("extract_claims", extract_claims)
    g.add_node("classify_claim", classify_claim)
    g.add_node("synthesize", synthesize)
    g.add_edge(START, "extract_claims")
    g.add_conditional_edges("extract_claims", fanout_claims, ["classify_claim"])
    g.add_edge("classify_claim", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


async def run_research_lg(query: str, book_slugs: list[str] | None) -> Report:
    initial: _ResearchState = {
        "query": query,
        "book_slugs": book_slugs,
        "claims_raw": [],
        "classified": [],
        "synthesis": "",
        "coverage_gaps": [],
    }
    final = await _graph().ainvoke(initial)

    claims_out: list[StanceClaim] = []
    for c in final.get("classified", []):
        ev_cit = [
            Citation(
                book=ev.get("book", ""),
                chapter=ev.get("chapter", ""),
                section=ev.get("section", ""),
            )
            for ev in c.get("evidence", [])
        ]
        raw_stance = c.get("stance", "BACKGROUND")
        if raw_stance not in ("SUPPORTS", "CONTRADICTS", "BACKGROUND"):
            raw_stance = "BACKGROUND"
        claims_out.append(StanceClaim(
            claim=c["text"],
            stance=raw_stance,  # type: ignore[arg-type]
            evidence=ev_cit,
            confidence=float(c.get("confidence", 0.0)),
        ))
    return Report(
        claims=claims_out,
        synthesis=final.get("synthesis", ""),
        coverage_gaps=final.get("coverage_gaps", []),
    )
