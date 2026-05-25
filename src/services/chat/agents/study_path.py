"""Mode 10 study path graph.

Pipeline:
  1. decompose_goal      — LLM splits the user's learning goal into 3-7 sub-objectives.
  2. invoke_prereqs      — for each sub-objective, call M5's run_prereqs to get a mini-DAG.
                           Merge DAGs into a unified concept ordering.
  3. sequence_curriculum — combine the topo ordering with retrieved sources to assign
                           concepts to weeks (target: 4-8 weeks, ~5 hours/week).
  4. coverage_gap_check  — for each sub-objective, mark missing-from-corpus concepts.

Chinese-wall: imports only from ``src.core.*`` and sibling chat modules.
"""
from __future__ import annotations

import asyncio
import json
import logging

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents.graph import Node, StateGraph
from src.services.chat.agents.prereqs import run_prereqs
from src.services.chat.agents.state import AgentState
from src.services.chat.retrieval import hybrid_search
from src.services.chat.schemas.output import Citation, StudyPlan, StudyWeek

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node 1 — decompose_goal
# ---------------------------------------------------------------------------


async def decompose_goal(state: AgentState) -> AgentState:
    """Split state.query into 3-7 sub-objectives. Stored in state.extras['sub_goals'].

    Args:
        state: The current agent state.

    Returns:
        Updated state with ``extras["sub_goals"]`` populated.  Sets
        ``qc_status = "fail"`` when the LLM returns an empty list.
    """
    prompt = (
        "A student wants to learn the following topic. Decompose it into 3-7 "
        "concrete sub-objectives ordered from foundational to advanced. Each "
        "sub-objective is a short noun phrase. Return ONLY JSON: "
        '{"goals": ["sub-goal 1", "sub-goal 2", ...]}\n\n'
        f"Topic: {state.query}"
    )
    oa = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await oa.chat.completions.create(
        model=settings.openai_model_nano,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.2,
    )
    raw = strip_fences(resp.choices[0].message.content or "{}")
    try:
        goals = json.loads(raw).get("goals", [])
    except json.JSONDecodeError:
        goals = []
    state.extras["sub_goals"] = [str(g) for g in goals[:7]]
    if not state.extras["sub_goals"]:
        state.qc_status = "fail"
    return state


# ---------------------------------------------------------------------------
# Node 2 — invoke_prereqs_subgraph
# ---------------------------------------------------------------------------


async def invoke_prereqs_subgraph(state: AgentState) -> AgentState:
    """Call M5's run_prereqs once per sub-goal; merge concepts + edges + cycles_broken.

    Each sub-goal is run against the same ``state.book_slugs`` scope.  Results
    are de-duplicated by concept id so the merged DAG has no repeated nodes.

    Args:
        state: The current agent state.  Reads ``extras["sub_goals"]``.

    Returns:
        Updated state with ``concepts``, ``edges``, and
        ``extras["cycles_broken"]`` merged from all sub-goal DAGs.
    """
    sub_goals: list[str] = state.extras.get("sub_goals", [])
    all_concepts: list[dict] = []
    all_edges: list[dict] = []
    cycles_broken: list[str] = []
    seen_ids: set[str] = set()

    for goal in sub_goals:
        try:
            dag = await run_prereqs(goal, state.book_slugs)
        except Exception:  # noqa: BLE001
            logger.exception("run_prereqs failed for %s", goal)
            continue
        for n in dag.nodes:
            if n.id not in seen_ids:
                seen_ids.add(n.id)
                all_concepts.append(
                    {
                        "id": n.id,
                        "label": n.label,
                        "source": n.source.model_dump() if n.source else None,
                    }
                )
        for e in dag.edges:
            all_edges.append({"from": e.from_id, "to": e.to_id, "weight": e.weight})
        cycles_broken.extend(dag.cycles_broken)

    state.concepts = all_concepts
    state.edges = all_edges
    state.extras["cycles_broken"] = cycles_broken
    return state


# ---------------------------------------------------------------------------
# Node 3 — sequence_curriculum
# ---------------------------------------------------------------------------


async def sequence_curriculum(state: AgentState) -> AgentState:
    """Topo-sort concepts then bucket into weeks based on estimated hours.

    Each concept needs ~1.5 hours; weeks have a ~5h cap.  Each StudyWeek
    references the concept's source citation dict.

    Args:
        state: The current agent state.  Reads ``concepts`` and ``edges``.

    Returns:
        Updated state with ``extras["weeks"]`` — a list of week dicts each
        containing ``week`` (int), ``sections`` (list[dict]), and
        ``hours_est`` (float).
    """
    # Build adjacency list + in-degree map for topological sort
    adj: dict[str, list[str]] = {c["id"]: [] for c in state.concepts}
    indeg: dict[str, int] = {c["id"]: 0 for c in state.concepts}
    for e in state.edges:
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

    id_to_concept = {c["id"]: c for c in state.concepts}
    weeks: list[dict] = []
    cur_week: dict = {"week": 1, "sections": [], "hours_est": 0.0}
    hours_cap = 5.0

    for cid in ordering:
        c = id_to_concept.get(cid) or {}
        src = c.get("source") or {}
        if cur_week["hours_est"] + 1.5 > hours_cap and cur_week["sections"]:
            weeks.append(cur_week)
            cur_week = {"week": len(weeks) + 1, "sections": [], "hours_est": 0.0}
        cur_week["sections"].append(src)
        cur_week["hours_est"] += 1.5

    if cur_week["sections"]:
        weeks.append(cur_week)

    state.extras["weeks"] = weeks
    return state


# ---------------------------------------------------------------------------
# Node 4 — coverage_gap_check
# ---------------------------------------------------------------------------


async def coverage_gap_check(state: AgentState) -> AgentState:
    """For each sub-goal, retrieve top-3; if max score < 0.4, mark as gap.

    Uses :func:`~src.services.chat.retrieval.hybrid_search` (sync) wrapped in
    ``asyncio.to_thread`` so the event loop is not blocked.

    Args:
        state: The current agent state.  Reads ``extras["sub_goals"]``.

    Returns:
        Updated state with ``extras["coverage_gaps"]`` — a list of sub-goal
        strings that had no high-confidence corpus match.
    """
    gaps: list[str] = []
    for goal in state.extras.get("sub_goals", []):
        try:
            srcs, _ = await asyncio.to_thread(
                hybrid_search,
                goal,
                book_slugs=state.book_slugs,
                top_k=3,
            )
            top = max((s.score for s in srcs), default=0.0)
            if top < 0.4:
                gaps.append(goal)
        except Exception:  # noqa: BLE001
            gaps.append(goal)
    state.extras["coverage_gaps"] = gaps
    return state


# ---------------------------------------------------------------------------
# Graph factory + public entry point
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Construct the study_path :class:`~src.services.chat.agents.graph.StateGraph`.

    Node pipeline:
    1. ``decompose_goal``   — LLM splits goal into 3-7 sub-objectives.
    2. ``invoke_prereqs``   — per-sub-goal prerequisite DAG (M5 reuse).
    3. ``sequence``         — topo-sort → week buckets.
    4. ``coverage_gaps``    — corpus coverage check.

    Returns:
        A :class:`~src.services.chat.agents.graph.StateGraph` ready to run.
    """
    return StateGraph(
        nodes=[
            Node("decompose_goal", decompose_goal),
            Node("invoke_prereqs", invoke_prereqs_subgraph),
            Node("sequence", sequence_curriculum),
            Node("coverage_gaps", coverage_gap_check),
        ],
        max_iters=15,
    )


async def run_study_path(
    query: str,
    book_slugs: list[str] | None,
    *,
    replanned_from_version: int = 0,
) -> StudyPlan:
    """Run the full study path graph and return a :class:`~src.services.chat.schemas.output.StudyPlan`.

    Builds a fresh :class:`~src.services.chat.agents.state.AgentState` for
    each call — no shared global state between invocations.

    Args:
        query: The user's top-level learning goal.
        book_slugs: Optional list of book slugs to scope retrieval.
        replanned_from_version: Previous plan version number; the new plan's
            ``replanned_from_version`` field will be set to this value.

    Returns:
        A :class:`~src.services.chat.schemas.output.StudyPlan` with weeks,
        coverage gaps, and the version lineage field populated.
    """
    state = AgentState(query=query, book_slugs=book_slugs)
    state = await build_graph().run(state)

    if state.errors:
        logger.warning("[study_path] completed with errors: %s", state.errors)

    weeks: list[StudyWeek] = [
        StudyWeek(
            week=w["week"],
            sections=[Citation(**s) for s in w["sections"] if s.get("book")],
            hours_est=w["hours_est"],
        )
        for w in state.extras.get("weeks", [])
    ]

    return StudyPlan(
        goal=query,
        weeks=weeks,
        total_weeks=len(weeks),
        coverage_gaps=state.extras.get("coverage_gaps", []),
        replanned_from_version=replanned_from_version,
    )
