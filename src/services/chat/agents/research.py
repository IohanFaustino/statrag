"""Mode 8 research graph.

Pipeline:
  1. extract_claims  — decompose user-pasted paper excerpt into atomic claims.
  2. per_claim_retrieve — for each claim, retrieve top-K chunks from the books.
  3. classify_stance — for each (claim, chunk) pair, label SUPPORTS/CONTRADICTS/BACKGROUND.
  4. synthesize — produce a Report with the synthesis paragraph + coverage_gaps.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
ADR-001: roll-own runner; no LangGraph.
"""
from __future__ import annotations

import asyncio
import json
import logging

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents.graph import Node, StateGraph
from src.services.chat.agents.state import AgentState
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas.output import Citation, Report, StanceClaim

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node 1 — extract_claims
# ---------------------------------------------------------------------------


async def extract_claims(state: AgentState) -> AgentState:
    """Decompose user input (``state.query``) into atomic factual claims.

    Calls the nano model to decompose a research excerpt into 3–8 standalone
    atomic claims.  Sets ``state.qc_status = "fail"`` when the LLM returns
    no parseable claims.

    Args:
        state: Current graph state; reads ``query`` (the raw user input).

    Returns:
        Updated state with ``claims`` list initialised.  Each entry is a dict::

            {
                "text": str,           # the claim text
                "evidence_sources": [],
                "stance": None,
                "confidence": 0.0,
                "evidence": [],
            }
    """
    prompt = (
        "Decompose the following research excerpt into 3-8 atomic factual claims. "
        "Each claim is a single short standalone statement. Return ONLY JSON: "
        '{"claims": ["claim 1", "claim 2", ...]}\n\n'
        f"Excerpt:\n{state.query[:4000]}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await oa.chat.completions.create(
        model=settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.1,
    )
    raw = strip_fences(resp.choices[0].message.content or "{}")
    try:
        claims_raw: list[str] = json.loads(raw).get("claims", [])
    except json.JSONDecodeError:
        claims_raw = []

    state.claims = [
        {
            "text": c,
            "evidence_sources": [],
            "stance": None,
            "confidence": 0.0,
            "evidence": [],
        }
        for c in claims_raw
        if isinstance(c, str) and c.strip()
    ]
    if not state.claims:
        state.qc_status = "fail"
        state.errors.append("extract_claims: LLM returned no parseable claims")
    return state


# ---------------------------------------------------------------------------
# Node 2 — per_claim_retrieve
# ---------------------------------------------------------------------------


async def per_claim_retrieve(state: AgentState) -> AgentState:
    """Run hybrid retrieval for each claim (sequential to bound cost).

    For each claim in ``state.claims`` calls
    :func:`~src.services.chat.retrieval.hybrid_search` with ``top_k=3`` and
    stores the resulting source dicts in ``claim["evidence_sources"]``.

    Args:
        state: Current graph state; reads ``claims`` and ``book_slugs``.

    Returns:
        Updated state with ``claim["evidence_sources"]`` populated for every
        claim.
    """
    for claim in state.claims:
        try:
            srcs, _ = await asyncio.to_thread(
                hybrid_search,
                claim["text"],
                book_slugs=state.book_slugs,
                top_k=3,
                rerank=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("per_claim_retrieve: retrieval failed for claim: %s", exc)
            srcs = []
        claim["evidence_sources"] = [
            {
                "book": s.book,
                "chapter": s.chapter,
                "section": s.section,
                "chunk": (s.chunk or "")[:1500],
                "score": s.score,
            }
            for s in srcs
        ]
    return state


# ---------------------------------------------------------------------------
# Node 3 — classify_stance
# ---------------------------------------------------------------------------


async def classify_stance(state: AgentState) -> AgentState:
    """For each (claim, evidence) pair, label stance and confidence.

    Issues one LLM call per claim; that call receives all evidence chunks for
    the claim simultaneously (up to 3).  The claim-level stance is determined
    by majority vote, with SUPPORTS/CONTRADICTS dominating BACKGROUND when any
    non-background result is present.

    Args:
        state: Current graph state; reads ``claims`` with ``evidence_sources``.

    Returns:
        Updated state with ``claim["stance"]``, ``claim["confidence"]``, and
        ``claim["evidence"]`` (top-2 sources by retrieval score) set for each
        claim.
    """
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    for claim in state.claims:
        ev_list: list[dict] = claim.get("evidence_sources", [])[:3]
        if not ev_list:
            claim["stance"] = "BACKGROUND"
            claim["confidence"] = 0.0
            claim["evidence"] = []
            continue

        evidence_blocks = "\n\n".join(
            f"EVIDENCE {i + 1}:\n{ev['chunk'][:1200]}"
            for i, ev in enumerate(ev_list)
        )
        prompt = (
            "Classify each EVIDENCE as SUPPORTS, CONTRADICTS, or BACKGROUND with "
            "respect to the CLAIM. SUPPORTS = evidence directly affirms the claim. "
            "CONTRADICTS = evidence disagrees or negates the claim. BACKGROUND = "
            "provides context but neither supports nor contradicts. "
            'Return ONLY JSON: {"results": [{"stance": "SUPPORTS|CONTRADICTS|BACKGROUND", '
            '"confidence": 0.0-1.0}, ...]}\n\n'
            f"CLAIM: {claim['text']}\n\n"
            f"{evidence_blocks}"
        )
        try:
            resp = await oa.chat.completions.create(
                model=settings.openai_model_nano,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.0,
            )
            raw = strip_fences(resp.choices[0].message.content or "{}")
            results: list[dict] = json.loads(raw).get("results", [])
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.warning("classify_stance: LLM call failed: %s", exc)
            results = []

        stances: list[str] = [r.get("stance", "BACKGROUND") for r in results]
        confs: list[float] = [float(r.get("confidence", 0.0)) for r in results]

        if not stances:
            claim["stance"] = "BACKGROUND"
            claim["confidence"] = 0.0
        else:
            non_bg = [
                (s, c) for s, c in zip(stances, confs) if s != "BACKGROUND"
            ]
            if non_bg:
                top_stance, top_conf = max(non_bg, key=lambda x: x[1])
                claim["stance"] = top_stance
                claim["confidence"] = top_conf
            else:
                claim["stance"] = "BACKGROUND"
                claim["confidence"] = max(confs, default=0.0)

        # Attach top-2 evidence citations sorted by retrieval score
        sorted_ev = sorted(ev_list, key=lambda x: -float(x.get("score", 0.0)))
        claim["evidence"] = sorted_ev[:2]

    return state


# ---------------------------------------------------------------------------
# Node 4 — synthesize_report
# ---------------------------------------------------------------------------


async def synthesize_report(state: AgentState) -> AgentState:
    """Produce a synthesis paragraph and coverage_gaps list.

    Sends a summary of all claims with their stances to the nano model and
    asks for a 4–6 sentence synthesis plus a list of claims with no supporting
    evidence (coverage gaps).

    Args:
        state: Current graph state; reads ``claims`` (with stance/confidence).

    Returns:
        Updated state with ``state.output`` set to a dict::

            {"synthesis": str, "coverage_gaps": list[str]}
    """
    claims_summary = "\n".join(
        f"- [{c.get('stance', 'BACKGROUND')}, "
        f"conf={c.get('confidence', 0.0):.2f}] {c['text']}"
        for c in state.claims
    )
    prompt = (
        "Below is a list of claims with their evidence stances from a textbook corpus. "
        "Write a 4-6 sentence synthesis paragraph that describes how the textbook corpus "
        "aligns with the excerpted research. Mention any claims with zero supporting "
        "evidence as coverage gaps. "
        'Return ONLY JSON: {"synthesis": "...", "coverage_gaps": ["claim text", ...]}\n\n'
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
        j: dict = json.loads(raw)
    except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
        logger.warning("synthesize_report: LLM call failed: %s", exc)
        j = {"synthesis": "", "coverage_gaps": []}

    state.output = {
        "synthesis": j.get("synthesis", ""),
        "coverage_gaps": j.get("coverage_gaps", []),
    }
    return state


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Construct and return the Mode 8 research :class:`StateGraph`.

    Returns:
        A :class:`StateGraph` with 4 nodes and ``max_iters=12``.
    """
    return StateGraph(
        nodes=[
            Node("extract_claims", extract_claims),
            Node("per_claim_retrieve", per_claim_retrieve),
            Node("classify_stance", classify_stance),
            Node("synthesize", synthesize_report),
        ],
        max_iters=12,
    )


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


async def run_research(
    query: str,
    book_slugs: list[str] | None,
) -> Report:
    """Execute the Mode 8 research pipeline and return a :class:`Report`.

    Creates a fresh :class:`AgentState`, runs the research graph, and
    assembles a :class:`Report` Pydantic model from the final state.

    Args:
        query: The raw user input — typically a pasted paper excerpt.
        book_slugs: Optional list of book slugs to restrict retrieval.

    Returns:
        A :class:`Report` with ``claims``, ``synthesis``, and
        ``coverage_gaps`` fields populated.
    """
    state = AgentState(query=query, book_slugs=book_slugs)
    state = await build_graph().run(state)

    claims_out: list[StanceClaim] = []
    for c in state.claims:
        ev_citations: list[Citation] = []
        for ev in c.get("evidence", []):
            ev_citations.append(
                Citation(
                    book=ev.get("book", ""),
                    chapter=ev.get("chapter", ""),
                    section=ev.get("section", ""),
                )
            )
        # Validate stance literal — fall back to BACKGROUND on bad values
        raw_stance: str = c.get("stance") or "BACKGROUND"
        if raw_stance not in ("SUPPORTS", "CONTRADICTS", "BACKGROUND"):
            raw_stance = "BACKGROUND"
        claims_out.append(
            StanceClaim(
                claim=c["text"],
                stance=raw_stance,  # type: ignore[arg-type]
                evidence=ev_citations,
                confidence=float(c.get("confidence", 0.0)),
            )
        )

    out: dict = state.output or {"synthesis": "", "coverage_gaps": []}
    return Report(
        claims=claims_out,
        synthesis=out.get("synthesis", ""),
        coverage_gaps=out.get("coverage_gaps", []),
    )
