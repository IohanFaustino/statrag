"""T11 acceptance: multi-agent modes on LangGraph + router dispatch."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from src.services.chat import router
from src.services.chat.schemas import ChatRequest


def _collect(gen):
    async def _run():
        out = []
        async for ev in gen:
            out.append(ev)
        return out

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# LangGraph graphs compile
# ---------------------------------------------------------------------------


def test_prereqs_lg_graph_compiles():
    from src.services.chat.agents.prereqs_lg import _graph
    g = _graph()
    assert g is not None
    nodes = list(g.get_graph().nodes.keys())
    assert {"retrieve", "extract_concepts", "build_dag", "cycle_detect", "sequence_topo"}.issubset(set(nodes))


def test_research_lg_graph_compiles():
    from src.services.chat.agents.research_lg import _graph
    g = _graph()
    nodes = list(g.get_graph().nodes.keys())
    assert {"extract_claims", "classify_claim", "synthesize"}.issubset(set(nodes))


def test_study_path_lg_graph_compiles():
    from src.services.chat.agents.study_path_lg import _graph
    g = _graph()
    nodes = list(g.get_graph().nodes.keys())
    assert {"decompose_goal", "invoke_prereqs", "sequence_curriculum", "coverage_gap_check"}.issubset(set(nodes))


# ---------------------------------------------------------------------------
# Router dispatch to LangGraph multi-agent
# ---------------------------------------------------------------------------


def test_prereqs_v2_dispatch(monkeypatch):
    from src.services.chat.schemas.output import DAG

    async def _stub_run(query, book_slugs):
        return DAG(target=query, nodes=[], edges=[], order=[], cycles_broken=[])

    monkeypatch.setattr(
        "src.services.chat.agents.prereqs_lg.run_prereqs_lg", _stub_run,
    )
    monkeypatch.setattr(router.settings, "use_v2_modes", ["prereqs"], raising=False)

    req = ChatRequest(message="explain OLS", mode="prereqs", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "DAG"
    assert types[-1] == "done"


def test_research_v2_dispatch(monkeypatch):
    from src.services.chat.schemas.output import Report

    async def _stub_run(query, book_slugs):
        return Report(claims=[], synthesis="", coverage_gaps=[])

    monkeypatch.setattr(
        "src.services.chat.agents.research_lg.run_research_lg", _stub_run,
    )
    monkeypatch.setattr(router.settings, "use_v2_modes", ["research"], raising=False)

    req = ChatRequest(message="excerpt", mode="research", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "Report"


def test_path_v2_dispatch(monkeypatch, tmp_path):
    from src.services.chat.schemas.output import StudyPlan
    from src.services.chat import store

    db = tmp_path / "chat.db"
    monkeypatch.setattr(store, "DB_PATH", db, raising=False)
    monkeypatch.setattr(store, "_db_initialised", False, raising=False)
    store.init_db()
    digest = store.create_conversation(
        title="t", mode="path", model_id="gpt-5.4-nano-2026-03-17", book_filter="ALL",
    )

    async def _stub_run(query, book_slugs, *, replanned_from_version=0):
        return StudyPlan(
            goal=query, weeks=[], total_weeks=0,
            coverage_gaps=[], replanned_from_version=replanned_from_version,
        )

    monkeypatch.setattr(
        "src.services.chat.agents.study_path_lg.run_study_path_lg", _stub_run,
    )
    monkeypatch.setattr(router.settings, "use_v2_modes", ["path"], raising=False)

    req = ChatRequest(
        message="learn statistics", mode="path",
        model="gpt-5.4-nano-2026-03-17", conversationId=digest.id,
    )
    events = _collect(router.stream_chat(req))
    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "StudyPlan"
    # Plan should be persisted to SQLite
    persisted = store.get_study_plan(digest.id)
    assert persisted is not None


def test_multi_agent_error_surfaces_as_sse_error(monkeypatch):
    async def _boom(query, book_slugs):
        raise RuntimeError("graph down")

    monkeypatch.setattr(
        "src.services.chat.agents.prereqs_lg.run_prereqs_lg", _boom,
    )
    monkeypatch.setattr(router.settings, "use_v2_modes", ["prereqs"], raising=False)

    req = ChatRequest(message="x", mode="prereqs", model="gpt-5.4-nano-2026-03-17")
    events = _collect(router.stream_chat(req))
    types = [e["type"] for e in events]
    assert "error" in types
    assert types[-1] == "done"
