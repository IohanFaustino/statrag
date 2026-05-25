"""Tests for Mode 10 study_path pipeline.

All LLM and Qdrant calls are mocked — no real network or DB connections.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat.agents.state import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_resp(content: str) -> MagicMock:
    """Build a minimal fake OpenAI response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_dag(nodes: list[dict], edges: list[dict]) -> MagicMock:
    """Build a minimal fake DAG object matching the DAG schema contract."""
    dag = MagicMock()

    concept_nodes = []
    for n in nodes:
        cn = MagicMock()
        cn.id = n["id"]
        cn.label = n.get("label", n["id"])
        src = n.get("source")
        if src:
            src_mock = MagicMock()
            src_mock.model_dump.return_value = src
            cn.source = src_mock
        else:
            cn.source = None
        concept_nodes.append(cn)
    dag.nodes = concept_nodes

    concept_edges = []
    for e in edges:
        ce = MagicMock()
        ce.from_id = e["from"]
        ce.to_id = e["to"]
        ce.weight = e.get("weight", 1.0)
        concept_edges.append(ce)
    dag.edges = concept_edges
    dag.cycles_broken = []
    return dag


# ---------------------------------------------------------------------------
# test_decompose_goal_parses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decompose_goal_parses() -> None:
    """decompose_goal correctly parses a JSON response with three goals."""
    from src.services.chat.agents.study_path import decompose_goal

    state = AgentState(query="learn statistical learning")
    fake_resp = _make_openai_resp('{"goals": ["g1", "g2", "g3"]}')

    fake_create = AsyncMock(return_value=fake_resp)
    fake_oa = MagicMock()
    fake_oa.chat.completions.create = fake_create

    with patch("src.services.chat.agents.study_path._openai.AsyncOpenAI", return_value=fake_oa):
        out = await decompose_goal(state)

    assert out.extras["sub_goals"] == ["g1", "g2", "g3"]
    assert out.qc_status != "fail"


@pytest.mark.asyncio
async def test_decompose_goal_empty_sets_fail() -> None:
    """decompose_goal sets qc_status='fail' when the LLM returns no goals."""
    from src.services.chat.agents.study_path import decompose_goal

    state = AgentState(query="learn something")
    fake_resp = _make_openai_resp('{"goals": []}')
    fake_create = AsyncMock(return_value=fake_resp)
    fake_oa = MagicMock()
    fake_oa.chat.completions.create = fake_create

    with patch("src.services.chat.agents.study_path._openai.AsyncOpenAI", return_value=fake_oa):
        out = await decompose_goal(state)

    assert out.qc_status == "fail"
    assert out.extras["sub_goals"] == []


@pytest.mark.asyncio
async def test_decompose_goal_bad_json() -> None:
    """decompose_goal sets qc_status='fail' when LLM returns unparseable text."""
    from src.services.chat.agents.study_path import decompose_goal

    state = AgentState(query="learn x")
    fake_resp = _make_openai_resp("not json at all")
    fake_create = AsyncMock(return_value=fake_resp)
    fake_oa = MagicMock()
    fake_oa.chat.completions.create = fake_create

    with patch("src.services.chat.agents.study_path._openai.AsyncOpenAI", return_value=fake_oa):
        out = await decompose_goal(state)

    assert out.qc_status == "fail"


# ---------------------------------------------------------------------------
# test_invoke_prereqs_subgraph — merges two DAGs, deduplicates nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_prereqs_merges_dags() -> None:
    """invoke_prereqs_subgraph merges nodes from two sub-goal DAGs and deduplicates."""
    from src.services.chat.agents.study_path import invoke_prereqs_subgraph

    dag1 = _make_dag(
        [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        [{"from": "a", "to": "b"}],
    )
    dag2 = _make_dag(
        [{"id": "b", "label": "B"}, {"id": "c", "label": "C"}],  # b repeated
        [{"from": "b", "to": "c"}],
    )

    state = AgentState(query="learn x")
    state.extras["sub_goals"] = ["goal1", "goal2"]

    async def fake_run_prereqs(query: str, book_slugs: Any) -> Any:
        return dag1 if query == "goal1" else dag2

    with patch("src.services.chat.agents.study_path.run_prereqs", side_effect=fake_run_prereqs):
        out = await invoke_prereqs_subgraph(state)

    concept_ids = {c["id"] for c in out.concepts}
    assert concept_ids == {"a", "b", "c"}  # b deduplicated
    assert len(out.edges) == 2


# ---------------------------------------------------------------------------
# test_sequence_curriculum_bucketing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequence_curriculum_bucketing() -> None:
    """6 concepts @ 1.5h each with 5h cap produce exactly 2 weeks (3+3)."""
    from src.services.chat.agents.study_path import sequence_curriculum

    concepts = [
        {"id": str(i), "label": f"C{i}", "source": {"book": "b", "chapter": "c1", "section": f"1.{i}"}}
        for i in range(6)
    ]
    # Linear chain: 0→1→2→3→4→5
    edges = [{"from": str(i), "to": str(i + 1), "weight": 1.0} for i in range(5)]

    state = AgentState(query="learn x")
    state.concepts = concepts
    state.edges = edges

    out = await sequence_curriculum(state)

    weeks = out.extras["weeks"]
    assert len(weeks) == 2
    assert weeks[0]["week"] == 1
    assert weeks[1]["week"] == 2
    # Total sections across both weeks = 6
    total_sections = sum(len(w["sections"]) for w in weeks)
    assert total_sections == 6


@pytest.mark.asyncio
async def test_sequence_curriculum_empty_concepts() -> None:
    """sequence_curriculum on empty state produces no weeks."""
    from src.services.chat.agents.study_path import sequence_curriculum

    state = AgentState(query="learn x")
    out = await sequence_curriculum(state)
    assert out.extras["weeks"] == []


# ---------------------------------------------------------------------------
# test_coverage_gap_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coverage_gap_check_marks_low_score() -> None:
    """coverage_gap_check marks a sub-goal as gap when max score < 0.4."""
    from src.services.chat.agents.study_path import coverage_gap_check

    state = AgentState(query="learn x")
    state.extras["sub_goals"] = ["easy_goal", "hard_goal"]

    def _fake_search(query: str, *, book_slugs: Any, top_k: int) -> tuple[list, Any]:
        if query == "easy_goal":
            src = MagicMock()
            src.score = 0.9
            return [src], MagicMock()
        # hard_goal → low score
        src = MagicMock()
        src.score = 0.1
        return [src], MagicMock()

    with patch("src.services.chat.agents.study_path.hybrid_search", side_effect=_fake_search):
        out = await coverage_gap_check(state)

    assert "hard_goal" in out.extras["coverage_gaps"]
    assert "easy_goal" not in out.extras["coverage_gaps"]


# ---------------------------------------------------------------------------
# test_run_study_path_persistence — mock store + LLM; verify version increments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_study_path_returns_study_plan() -> None:
    """run_study_path returns a StudyPlan with the correct replanned_from_version."""
    from src.services.chat.agents.study_path import run_study_path
    from src.services.chat.schemas.output import StudyPlan

    async def _mock_run(q: str, slugs: Any, *, replanned_from_version: int = 0) -> StudyPlan:
        return StudyPlan(
            goal=q,
            weeks=[],
            total_weeks=0,
            coverage_gaps=[],
            replanned_from_version=replanned_from_version,
        )

    with patch("src.services.chat.agents.study_path.build_graph") as mock_build:
        graph = MagicMock()

        async def _fake_graph_run(state: AgentState) -> AgentState:
            state.extras.setdefault("weeks", [])
            state.extras.setdefault("coverage_gaps", [])
            return state

        graph.run = _fake_graph_run
        mock_build.return_value = graph

        plan = await run_study_path("learn probability", None, replanned_from_version=2)

    assert isinstance(plan, StudyPlan)
    assert plan.goal == "learn probability"
    assert plan.replanned_from_version == 2


# ---------------------------------------------------------------------------
# test_replan_increments_version — POST /api/study_plans/{id}/replan
# ---------------------------------------------------------------------------


def test_replan_increments_version(tmp_path: Any, monkeypatch: Any) -> None:
    """POST /replan returns a plan with replanned_from_version = prev + 1 and persists it."""
    import src.services.chat.store as store_mod
    from fastapi.testclient import TestClient

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "chat.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    # Seed an existing plan at version 3
    store_mod.upsert_study_plan(
        "conv-replan-1",
        {"goal": "original", "weeks": [], "total_weeks": 0, "coverage_gaps": [], "replanned_from_version": 0},
        version=3,
    )

    from src.services.chat.schemas.output import StudyPlan

    async def _stub_run(query: str, book_slugs: Any, *, replanned_from_version: int = 0) -> StudyPlan:
        return StudyPlan(
            goal=query,
            weeks=[],
            total_weeks=0,
            coverage_gaps=[],
            replanned_from_version=replanned_from_version,
        )

    from src.services.chat import api as api_mod

    monkeypatch.setattr(
        "src.services.chat.agents.study_path.run_study_path",
        _stub_run,
    )

    with TestClient(api_mod.app) as client:
        resp = client.post(
            "/api/study_plans/conv-replan-1/replan",
            json={"message": "new goal", "bookFilter": "ALL"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["replanned_from_version"] == 3  # prev version passed in

    # Verify persistence incremented to 4
    saved = store_mod.get_study_plan("conv-replan-1")
    assert saved is not None
    assert saved["version"] == 4


# ---------------------------------------------------------------------------
# test_delete_section_replans — DELETE /api/study_plans/{id}/section/{ref}
# ---------------------------------------------------------------------------


def test_delete_section_replans(tmp_path: Any, monkeypatch: Any) -> None:
    """DELETE /section/{ref} removes the citation and triggers a replan."""
    import src.services.chat.store as store_mod
    from fastapi.testclient import TestClient

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "chat2.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    plan_data = {
        "goal": "learn regression",
        "weeks": [
            {
                "week": 1,
                "sections": [
                    {"book": "islp", "chapter": "ch03", "section": "3.1", "page": None, "chunk_id": ""},
                    {"book": "islp", "chapter": "ch03", "section": "3.2", "page": None, "chunk_id": ""},
                ],
                "goals": [],
                "hours_est": 3.0,
            }
        ],
        "total_weeks": 1,
        "coverage_gaps": [],
        "replanned_from_version": 0,
    }
    store_mod.upsert_study_plan("conv-del-1", plan_data, version=1)

    from src.services.chat.schemas.output import StudyPlan

    async def _stub_run(query: str, book_slugs: Any, *, replanned_from_version: int = 0) -> StudyPlan:
        return StudyPlan(
            goal=query,
            weeks=[],
            total_weeks=0,
            coverage_gaps=[],
            replanned_from_version=replanned_from_version,
        )

    monkeypatch.setattr(
        "src.services.chat.agents.study_path.run_study_path",
        _stub_run,
    )

    from src.services.chat import api as api_mod

    with TestClient(api_mod.app) as client:
        resp = client.delete("/api/study_plans/conv-del-1/section/islp__ch03__3.1")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)

    # Version bumped
    saved = store_mod.get_study_plan("conv-del-1")
    assert saved is not None
    assert saved["version"] == 2


# ---------------------------------------------------------------------------
# test_api_get_study_plan_not_found
# ---------------------------------------------------------------------------


def test_api_get_study_plan_not_found(tmp_path: Any, monkeypatch: Any) -> None:
    """GET /api/study_plans/{id} returns 404 for unknown conv_id."""
    import src.services.chat.store as store_mod
    from fastapi.testclient import TestClient

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "chat3.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    from src.services.chat import api as api_mod

    with TestClient(api_mod.app) as client:
        resp = client.get("/api/study_plans/nonexistent-conv")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_api_get_study_plan_found
# ---------------------------------------------------------------------------


def test_api_get_study_plan_found(tmp_path: Any, monkeypatch: Any) -> None:
    """GET /api/study_plans/{id} returns the stored plan."""
    import src.services.chat.store as store_mod
    from fastapi.testclient import TestClient

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "chat4.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    plan_data = {
        "goal": "learn x",
        "weeks": [],
        "total_weeks": 0,
        "coverage_gaps": [],
        "replanned_from_version": 0,
    }
    store_mod.upsert_study_plan("conv-get-1", plan_data, version=1)

    from src.services.chat import api as api_mod

    with TestClient(api_mod.app) as client:
        resp = client.get("/api/study_plans/conv-get-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert data["state_json"]["goal"] == "learn x"


# ---------------------------------------------------------------------------
# test_store_crud
# ---------------------------------------------------------------------------


def test_store_study_plan_crud(tmp_path: Any, monkeypatch: Any) -> None:
    """upsert / get / delete round-trip for study_plans table."""
    import src.services.chat.store as store_mod

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "chat5.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    plan = {"goal": "test", "weeks": [], "total_weeks": 0, "coverage_gaps": [], "replanned_from_version": 0}
    store_mod.upsert_study_plan("cv1", plan, version=1)

    record = store_mod.get_study_plan("cv1")
    assert record is not None
    assert record["version"] == 1
    assert record["state_json"]["goal"] == "test"

    # Upsert again with higher version
    store_mod.upsert_study_plan("cv1", {**plan, "goal": "updated"}, version=2)
    record2 = store_mod.get_study_plan("cv1")
    assert record2 is not None
    assert record2["version"] == 2
    assert record2["state_json"]["goal"] == "updated"

    # Delete
    deleted = store_mod.delete_study_plan("cv1")
    assert deleted is True
    assert store_mod.get_study_plan("cv1") is None

    # Delete non-existent
    not_deleted = store_mod.delete_study_plan("cv1")
    assert not_deleted is False


# ---------------------------------------------------------------------------
# test_orchestrator_path_mode — mode == "path" dispatches to run_study_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_path_mode(tmp_path: Any, monkeypatch: Any) -> None:
    """stream_chat with mode='path' yields meta + structured_output + done."""
    import src.services.chat.store as store_mod

    monkeypatch.setattr(store_mod, "DB_PATH", tmp_path / "orch.db")
    store_mod._db_initialised = False
    store_mod.init_db()

    from src.services.chat.schemas import ChatRequest
    from src.services.chat.schemas.output import StudyPlan

    async def _stub_run(query: str, book_slugs: Any, *, replanned_from_version: int = 0) -> StudyPlan:
        return StudyPlan(
            goal=query,
            weeks=[],
            total_weeks=0,
            coverage_gaps=[],
            replanned_from_version=replanned_from_version,
        )

    with patch("src.services.chat.agents.study_path.run_study_path", _stub_run):
        from src.services.chat.orchestrator import stream_chat

        req = ChatRequest(
            message="learn Bayesian inference",
            mode="path",
            model="nano",
            bookFilter="ALL",
            conversationId=None,
        )
        events = [ev async for ev in stream_chat(req)]

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert "structured_output" in types
    assert types[-1] == "done"

    so = next(e for e in events if e["type"] == "structured_output")
    assert so["schema"] == "StudyPlan"
    assert so["data"]["goal"] == "learn Bayesian inference"
