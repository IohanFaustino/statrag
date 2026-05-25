"""Tests for mode registry, output schemas, and schema-repair loop.

All external I/O (Qdrant, OpenAI) is mocked.  Tests run fully offline.

Coverage:
- All 11 modes registered with correct id and non-empty system prompt.
- Output schemas validate against hand-crafted fixtures.
- Schema-repair retry path in orchestrator rescues invalid JSON.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncIterator

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on PYTHONPATH and a dummy API key is present
# ---------------------------------------------------------------------------

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect(coro) -> list[dict]:  # type: ignore[return]
    """Drain an async generator into a plain list synchronously."""

    async def _inner():
        return [ev async for ev in coro]

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _make_source(rank: int = 1):
    """Return a minimal Source fixture."""
    import uuid

    from src.services.chat.schemas import Source

    return Source(
        rank=rank,
        book="islp",
        chapter="ch01",
        section="1.1",
        title="Introduction",
        excerpt="Short excerpt.",
        score=0.9,
        page=1,
        chunkId=uuid.uuid4().hex,
        chunk="Full chunk text about linear regression and statistics.",
        highlights=[],
    )


def _make_metadata():
    """Return a minimal RetrievalMetadata fixture."""
    from src.services.chat.schemas import RetrievalMetadata

    return RetrievalMetadata(
        rewrittenQuery="what is regression",
        embedding="text-embedding-3-large",
        retrievalMs=50,
        collections=["introduction_textbooks"],
        filter="none",
        topK=5,
        scoreThreshold=0.0,
        mode="hybrid (RRF: dense + sparse)",
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_has_11() -> None:
    """ModeRegistry must contain exactly 11 entries after registration."""
    from src.services.chat.modes import ModeRegistry, register_all_modes

    register_all_modes()
    assert len(ModeRegistry.all()) == 11


@pytest.mark.parametrize(
    "mode_id",
    [
        "tutor",
        "compare",
        "figures",
        "quiz",
        "navigate",
        "prereqs",
        "annotate",
        "research",
        "math",
        "path",
        "roadmap",
    ],
)
def test_each_mode_registered(mode_id: str) -> None:
    """Every canonical mode ID must be registered with a non-empty system prompt."""
    from src.services.chat.modes import ModeRegistry

    spec = ModeRegistry.get(mode_id)
    assert spec.id == mode_id
    assert spec.system_prompt, f"Mode {mode_id!r} has empty system_prompt"


def test_mode_output_schemas_are_distinct() -> None:
    """Most modes should declare different output schemas."""
    from src.services.chat.modes import ModeRegistry

    schemas = [spec.output_schema for spec in ModeRegistry.all()]
    # At minimum there should be more than 1 unique schema
    assert len(set(schemas)) > 1


def test_multi_agent_modes() -> None:
    """prereqs, research, path must use arch='multi'."""
    from src.services.chat.modes import ModeRegistry

    for mode_id in ("prereqs", "research", "path"):
        spec = ModeRegistry.get(mode_id)
        assert spec.arch == "multi", f"{mode_id} should be arch=multi"


def test_single_agent_modes() -> None:
    """tutor, compare, figures, quiz, navigate, annotate, math, roadmap → single."""
    from src.services.chat.modes import ModeRegistry

    for mode_id in (
        "tutor", "compare", "figures", "quiz", "navigate",
        "annotate", "math", "roadmap",
    ):
        spec = ModeRegistry.get(mode_id)
        assert spec.arch == "single", f"{mode_id} should be arch=single"


def test_vision_modes_use_pro_vision() -> None:
    """figures and math must use model='pro_vision'."""
    from src.services.chat.modes import ModeRegistry

    for mode_id in ("figures", "math"):
        spec = ModeRegistry.get(mode_id)
        assert spec.model == "pro_vision", f"{mode_id} should use pro_vision"


def test_path_mode_memory_persist() -> None:
    """path mode must use memory='persist'."""
    from src.services.chat.modes import ModeRegistry

    spec = ModeRegistry.get("path")
    assert spec.memory == "persist"


def test_tutor_mode_memory_auto() -> None:
    """tutor mode must use memory='auto'."""
    from src.services.chat.modes import ModeRegistry

    spec = ModeRegistry.get("tutor")
    assert spec.memory == "auto"


def test_register_all_modes_is_idempotent() -> None:
    """Calling register_all_modes() twice must not duplicate registrations."""
    from src.services.chat.modes import ModeRegistry, register_all_modes

    register_all_modes()
    count_after_double_call = len(ModeRegistry.all())
    assert count_after_double_call == 11


# ---------------------------------------------------------------------------
# Schema fixture tests
# ---------------------------------------------------------------------------


def test_quiz_schema_fixture() -> None:
    """Quiz schema must accept a hand-crafted valid fixture."""
    from src.services.chat.schemas.output import Citation, Question, Quiz

    q = Quiz(
        questions=[
            Question(
                stem="What is the bias-variance tradeoff?",
                options=[
                    "Tradeoff between model complexity and error",
                    "Tradeoff between speed and accuracy",
                    "Tradeoff between CPU and memory",
                    "None of the above",
                ],
                answer_idx=0,
                rubric="The bias-variance tradeoff balances model complexity against generalisation error.",
                source=Citation(book="islp", chapter="ch02", section="2.2"),
                difficulty="medium",
            )
        ]
    )
    assert q.questions[0].answer_idx == 0
    assert q.questions[0].difficulty == "medium"


def test_dag_schema_fixture() -> None:
    """DAG schema must accept a valid prerequisite graph fixture."""
    from src.services.chat.schemas.output import Citation, ConceptEdge, ConceptNode, DAG

    dag = DAG(
        target="linear regression",
        nodes=[
            ConceptNode(id="prob", label="Probability"),
            ConceptNode(
                id="linreg",
                label="Linear Regression",
                source=Citation(book="islp", chapter="ch03", section="3.1"),
            ),
        ],
        edges=[ConceptEdge(from_id="prob", to_id="linreg", weight=1.0)],
        order=["prob", "linreg"],
        cycles_broken=[],
    )
    assert len(dag.nodes) == 2
    assert dag.edges[0].from_id == "prob"


def test_tutor_answer_schema_fixture() -> None:
    """TutorAnswer must accept a minimal valid fixture.

    T13-E: citations are now :class:`TutorCitation` (numbered, with quote
    + provenance) instead of plain :class:`Citation`.
    """
    from src.services.chat.schemas.output import TutorAnswer, TutorCitation

    ans = TutorAnswer(
        text="Linear regression models the relationship between X and Y.[1]",
        sections=["Definition"],
        citations=[TutorCitation(
            index=1, chunkId="c-1",
            authors_short="James et al.", year=2023,
            book_name="ISL", chapter="ch03", section="3.1",
            page_from=59, page_to=62,
            quote="Linear regression models the relationship between X and Y.",
        )],
    )
    assert ans.text.startswith("Linear")
    assert ans.citations[0].authors_short == "James et al."


def test_roadmap_schema_fixture() -> None:
    """Roadmap schema must accept a hand-crafted scene list."""
    from src.services.chat.schemas.output import Citation, Roadmap, Scene

    roadmap = Roadmap(
        topic="Introduction to Regression",
        target_audience="graduate students",
        total_duration_estimate="20 min",
        duration_total_min=20,
        scenes=[
            Scene(
                id=1,
                title="What is regression?",
                concept="linear regression",
                source=Citation(book="islp", chapter="ch03", section="3.1"),
                suggested_visual="scatter plot of X vs Y with fitted line",
                duration_hint="3 min",
                figure=None,
            )
        ],
    )
    assert roadmap.scenes[0].id == 1


def test_study_plan_schema_fixture() -> None:
    """StudyPlan must accept a minimal weekly plan fixture."""
    from src.services.chat.schemas.output import Citation, StudyPlan, StudyWeek

    plan = StudyPlan(
        goal="Understand linear models",
        weeks=[
            StudyWeek(
                week=1,
                sections=[Citation(book="islp", chapter="ch03", section="3.1")],
                goals=["Understand simple linear regression"],
                hours_est=3.0,
            )
        ],
        total_weeks=1,
    )
    assert plan.weeks[0].week == 1


# ---------------------------------------------------------------------------
# Schema-repair path test
# ---------------------------------------------------------------------------


def test_schema_repair_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Orchestrator must recover when first LLM response is invalid JSON.

    Setup: first stream call yields invalid JSON; second (repair) call yields
    valid Quiz JSON.  Expect a structured_output event in the stream.
    """
    from src.services.chat.llm.base import BaseLLM
    from src.services.chat.schemas import ChatRequest
    from src.services.chat.schemas.output import Citation, Question, Quiz

    # Build a valid Quiz JSON fixture
    valid_quiz = Quiz(
        questions=[
            Question(
                stem="What is OLS?",
                options=["A method", "A model", "A statistic", "A test"],
                answer_idx=0,
                rubric="OLS minimises squared residuals.",
                source=Citation(book="islp", chapter="ch03", section="3.1"),
                difficulty="easy",
            )
        ]
    )
    valid_json = valid_quiz.model_dump_json()

    call_count = 0

    class _TwoPassLLM(BaseLLM):
        """First call yields invalid JSON; second call yields valid JSON."""

        async def stream(self, messages, *, model, temperature=0.2, max_tokens=None, response_format=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First pass: invalid JSON
                for chunk in ["NOT VALID JSON {{{]::"]:
                    yield chunk
            else:
                # Repair pass: valid JSON
                for chunk in [valid_json]:
                    yield chunk

    def _fake_get_llm(model_id: str):
        return _TwoPassLLM(), model_id

    def _fake_search(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, **_kw):
        return [_make_source()], _make_metadata()

    def _fake_figures(query, book_slugs=None, k=2):
        return []

    def _fake_highlights(query, chunk, max_spans=2):
        return []

    async def _fake_expand(query, *, flags):
        return [query]

    monkeypatch.setattr("src.services.chat.orchestrator.get_llm", _fake_get_llm)
    monkeypatch.setattr("src.services.chat.orchestrator.hybrid_search", _fake_search)
    monkeypatch.setattr("src.services.chat.orchestrator.search_figures", _fake_figures)
    monkeypatch.setattr(
        "src.services.chat.orchestrator.compute_highlights", _fake_highlights
    )
    monkeypatch.setattr("src.services.chat.orchestrator.expand_queries", _fake_expand)

    from src.services.chat.orchestrator import stream_chat

    # Use quiz mode so that schema validation triggers
    req = ChatRequest(message="generate a quiz on OLS", mode="quiz")
    events = _collect(stream_chat(req))

    types = [e["type"] for e in events]
    assert "done" in types, "stream must always end with done"

    # Expect structured_output event (repair succeeded)
    structured_events = [e for e in events if e["type"] == "structured_output"]
    assert structured_events, (
        "Expected structured_output event after repair. "
        f"Got event types: {types}"
    )
    assert structured_events[0]["schema"] == "Quiz"


def test_schema_repair_double_failure_emits_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both attempts fail, orchestrator must emit error + done."""
    from src.services.chat.llm.base import BaseLLM
    from src.services.chat.schemas import ChatRequest

    class _AlwaysBrokenLLM(BaseLLM):
        async def stream(self, messages, *, model, temperature=0.2, max_tokens=None, response_format=None):
            yield "totally invalid }{{"

    def _fake_get_llm(model_id: str):
        return _AlwaysBrokenLLM(), model_id

    def _fake_search(query, *, book_slugs=None, top_k=5, rerank=False, rerank_top_n=None, **_kw):
        return [_make_source()], _make_metadata()

    async def _fake_expand(query, *, flags):
        return [query]

    monkeypatch.setattr("src.services.chat.orchestrator.get_llm", _fake_get_llm)
    monkeypatch.setattr("src.services.chat.orchestrator.hybrid_search", _fake_search)
    monkeypatch.setattr(
        "src.services.chat.orchestrator.search_figures", lambda *a, **kw: []
    )
    monkeypatch.setattr(
        "src.services.chat.orchestrator.compute_highlights", lambda *a, **kw: []
    )
    monkeypatch.setattr("src.services.chat.orchestrator.expand_queries", _fake_expand)

    from src.services.chat.orchestrator import stream_chat

    req = ChatRequest(message="quiz on bias-variance", mode="quiz")
    events = _collect(stream_chat(req))
    types = [e["type"] for e in events]

    assert "error" in types
    assert types[-1] == "done"
