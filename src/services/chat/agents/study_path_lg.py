"""LangGraph re-implementation of the ``path`` multi-agent graph (T11).

Pipeline:

  decompose_goal
       └─► (Send per sub-goal) ─► invoke_prereqs ─► merge
                                                   └─► sequence_curriculum
                                                         └─► coverage_gap_check
                                                              └─► END

Per-sub-goal calls to :func:`agents.prereqs_lg.run_prereqs_lg` run in parallel
via ``Send`` fan-out — replacing the v1 serial loop.

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
from src.services.chat.agents.prereqs_lg import run_prereqs_lg
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas.output import Citation, StudyPlan, StudyWeek

logger = logging.getLogger(__name__)


class _PathState(TypedDict, total=False):
    query: str
    book_slugs: list[str] | None
    sub_goals: list[str]
    sub_concepts: Annotated[list[dict], operator.add]
    sub_edges: Annotated[list[dict], operator.add]
    cycles_broken: Annotated[list[str], operator.add]
    weeks: list[dict]
    coverage_gaps: list[str]


async def decompose_goal(state: _PathState) -> dict:
    prompt = (
        "A student wants to learn the following topic. Decompose it into 3-7 "
        "concrete sub-objectives ordered from foundational to advanced. Each "
        "sub-objective is a short noun phrase. Return ONLY JSON: "
        '{"goals": ["sub-goal 1", "sub-goal 2", ...]}\n\n'
        f"Topic: {state.get('query', '')}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await oa.chat.completions.create(
            model=settings.openai_model_nano,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        goals = json.loads(raw).get("goals", [])
    except Exception:  # noqa: BLE001
        logger.exception("path_lg.decompose_goal failed")
        goals = []
    return {"sub_goals": [str(g) for g in goals[:7]]}


def fanout_subgoals(state: _PathState):
    book_slugs = state.get("book_slugs")
    return [
        Send("invoke_prereqs", {"goal": g, "book_slugs": book_slugs})
        for g in state.get("sub_goals", [])
    ]


async def invoke_prereqs(payload: dict) -> dict:
    """Worker: call the prereqs subgraph for one sub-goal."""
    goal: str = payload["goal"]
    book_slugs: list[str] | None = payload.get("book_slugs")
    try:
        dag = await run_prereqs_lg(goal, book_slugs)
    except Exception:  # noqa: BLE001
        logger.exception("path_lg.invoke_prereqs failed for %s", goal)
        return {"sub_concepts": [], "sub_edges": [], "cycles_broken": []}

    concepts = [{
        "id": n.id,
        "label": n.label,
        "source": n.source.model_dump() if n.source else None,
    } for n in dag.nodes]
    edges = [{"from": e.from_id, "to": e.to_id, "weight": e.weight} for e in dag.edges]
    return {
        "sub_concepts": concepts,
        "sub_edges": edges,
        "cycles_broken": list(dag.cycles_broken),
    }


async def sequence_curriculum(state: _PathState) -> dict:
    """Topo-sort + week packing (1.5h/concept, 5h/week cap)."""
    # Dedupe concepts by id (parallel workers may emit duplicates).
    seen: set[str] = set()
    concepts: list[dict] = []
    for c in state.get("sub_concepts", []):
        cid = c.get("id")
        if cid and cid not in seen:
            seen.add(cid)
            concepts.append(c)

    edges = state.get("sub_edges", [])
    adj: dict[str, list[str]] = {c["id"]: [] for c in concepts}
    indeg: dict[str, int] = {c["id"]: 0 for c in concepts}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in adj and t in adj:
            adj[f].append(t)
            indeg[t] += 1

    queue: list[str] = [n for n, d in indeg.items() if d == 0]
    ordering: list[str] = []
    while queue:
        u = queue.pop(0)
        ordering.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)

    id_to_c = {c["id"]: c for c in concepts}
    weeks: list[dict] = []
    cur = {"week": 1, "sections": [], "hours_est": 0.0}
    cap = 5.0
    for cid in ordering:
        c = id_to_c.get(cid, {})
        src = c.get("source") or {}
        if cur["hours_est"] + 1.5 > cap and cur["sections"]:
            weeks.append(cur)
            cur = {"week": len(weeks) + 1, "sections": [], "hours_est": 0.0}
        cur["sections"].append(src)
        cur["hours_est"] += 1.5
    if cur["sections"]:
        weeks.append(cur)
    return {"weeks": weeks}


async def coverage_gap_check(state: _PathState) -> dict:
    gaps: list[str] = []
    for goal in state.get("sub_goals", []):
        try:
            srcs, _ = await asyncio.to_thread(
                hybrid_search, goal, book_slugs=state.get("book_slugs"), top_k=3,
            )
            top = max((s.score for s in srcs), default=0.0)
            if top < 0.4:
                gaps.append(goal)
        except Exception:  # noqa: BLE001
            gaps.append(goal)
    return {"coverage_gaps": gaps}


def _build_graph():
    g = StateGraph(_PathState)
    g.add_node("decompose_goal", decompose_goal)
    g.add_node("invoke_prereqs", invoke_prereqs)
    g.add_node("sequence_curriculum", sequence_curriculum)
    g.add_node("coverage_gap_check", coverage_gap_check)
    g.add_edge(START, "decompose_goal")
    g.add_conditional_edges("decompose_goal", fanout_subgoals, ["invoke_prereqs"])
    g.add_edge("invoke_prereqs", "sequence_curriculum")
    g.add_edge("sequence_curriculum", "coverage_gap_check")
    g.add_edge("coverage_gap_check", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


async def run_study_path_lg(
    query: str,
    book_slugs: list[str] | None,
    *,
    replanned_from_version: int = 0,
) -> StudyPlan:
    initial: _PathState = {
        "query": query,
        "book_slugs": book_slugs,
        "sub_goals": [],
        "sub_concepts": [],
        "sub_edges": [],
        "cycles_broken": [],
        "weeks": [],
        "coverage_gaps": [],
    }
    final = await _graph().ainvoke(initial)

    weeks: list[StudyWeek] = [
        StudyWeek(
            week=w["week"],
            sections=[Citation(**s) for s in w["sections"] if s.get("book")],
            hours_est=w["hours_est"],
        )
        for w in final.get("weeks", [])
    ]
    return StudyPlan(
        goal=query,
        weeks=weeks,
        total_weeks=len(weeks),
        coverage_gaps=final.get("coverage_gaps", []),
        replanned_from_version=replanned_from_version,
    )
