"""Tests for the orchestrator-workers (per-author) drafting workflow."""
import asyncio

import pytest

from src.services.chat.agents import deep_tutor as d
import src.services.chat.agents.orchestrator_workers as OW
from src.services.chat.schemas import ChatRequest, Source
from src.services.chat.schemas.output import AuthorBrief, DeepTutorAnswer, SynthesisPlan, WorkerTask


def _src(rank, author, book):
    return Source(
        rank=rank, chunkId=f"c{rank}", title="t", excerpt="x", chunk="hello",
        book=book, book_name=book, authors=f"A {author}", authors_short=author,
        section="1", chapter="ch1", score=0.5,
    )


def test_group_sources_by_author():
    g = OW._group_sources_by_author([
        _src(1, "Smith", "b1"), _src(2, "Jones", "b2"), _src(3, "Smith", "b1"),
    ])
    assert {k: len(v) for k, v in g.items()} == {"smith": 2, "jones": 1}


class TestResolveWorkflow:
    def test_default_single(self):
        assert d._resolve_workflow(ChatRequest(message="q")) == "single"

    def test_request_orchestrator(self):
        assert d._resolve_workflow(
            ChatRequest(message="q", tutorWorkflow="orchestrator")) == "orchestrator"


def test_resolve_workflow_passes_orchestrator_deep():
    from types import SimpleNamespace
    import src.services.chat.agents.deep_tutor as DT
    assert DT._resolve_workflow(SimpleNamespace(tutorWorkflow="orchestrator-deep")) == "orchestrator-deep"
    assert DT._resolve_workflow(SimpleNamespace(tutorWorkflow="single")) == "single"


@pytest.mark.asyncio
async def test_worker_graceful_on_failure(monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                async def parse(*a, **k):
                    raise RuntimeError("boom")
    monkeypatch.setattr(OW, "_async_client", lambda *_a, **_k: _Boom())
    out = await OW.run_author_worker("q", "thesis", "Smith", [_src(1, "Smith", "b1")])
    assert out is None


def test_fallback_tasks_per_author():
    tasks = OW._fallback_tasks([_src(1, "Smith", "b1"), _src(2, "Jones", "b2"), _src(3, "Smith", "b1")])
    assert {t.focus for t in tasks} == {"Smith", "Jones"}
    smith = next(t for t in tasks if t.focus == "Smith")
    assert sorted(smith.source_ranks) == [1, 3]


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_single_author():
    # No plan tasks -> per-author fallback -> 1 author -> (None, {}).
    out, aspects = await OW.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Smith", "b1")], None,
    )
    assert out is None and aspects == {}


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_all_workers_fail(monkeypatch):
    async def _none(*a, **k):
        return None
    monkeypatch.setattr(OW, "run_author_worker", _none)
    # plan has no tasks -> per-author fallback (2 authors) -> all workers fail.
    out, _ = await OW.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Jones", "b2")], SynthesisPlan(thesis="T"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_orchestrator_uses_planner_tasks(monkeypatch):
    # The Planner's tasks (plan.tasks) drive the workers — no second LLM call.
    seen = []
    async def _worker(query, thesis, focus, srcs, *, model=None):
        seen.append(focus)
        return AuthorBrief(author=focus, summary="s", key_points=["p"], source_ranks=[srcs[0].rank])
    async def _synth(messages, model, on_aspect_delta=None):
        return DeepTutorAnswer(tldr="x", definition="d", formal_statement="f",
                               example_intuition="ei", applications="a",
                               further_reading="r"), {}
    monkeypatch.setattr(OW, "run_author_worker", _worker)
    monkeypatch.setattr(OW, "_stream_structured", _synth)
    plan = SynthesisPlan(thesis="T", tasks=[
        WorkerTask(focus="view A", source_ranks=[1]),
        WorkerTask(focus="view B", source_ranks=[2]),
    ])
    out, _ = await OW.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Jones", "b2")], plan,
    )
    assert out is not None
    assert seen == ["view A", "view B"]  # planner-chosen foci drove the workers


def test_format_author_briefs():
    txt = OW._format_author_briefs([
        AuthorBrief(author="Smith", summary="S", key_points=["p1"], source_ranks=[1, 3]),
    ])
    assert "<author_briefs>" in txt and "author='Smith'" in txt and "#1, #3" in txt


def test_schema_fill_calls_stream_structured_with_synthesis_text(monkeypatch):
    captured = {}

    async def fake_stream(messages, model, on_aspect_delta):
        captured["messages"] = messages
        captured["model"] = model
        return DeepTutorAnswer(tldr="t", definition="d", formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {"definition": "d"}

    monkeypatch.setattr(OW, "_stream_structured", fake_stream)
    deep, aspects = asyncio.run(
        OW._schema_fill("What is variance?", "SYNTH TEXT", "nano", None)
    )
    assert deep is not None and deep.tldr == "t"
    blob = "".join(m["content"] for m in captured["messages"])
    assert "SYNTH TEXT" in blob and "What is variance?" in blob
    assert captured["model"] == "nano"


# ---------------------------------------------------------------------------
# Task 3: L5 / deep_synth tests
# ---------------------------------------------------------------------------

def _two_author_inputs():
    sources = [
        Source(rank=1, book="b1", chapter="1", section="s", excerpt="x",
               authors_short="Casella", title="t", score=0.5, chunkId="c1", chunk="x"),
        Source(rank=2, book="b2", chapter="1", section="s", excerpt="y",
               authors_short="Wasserman", title="t", score=0.5, chunkId="c2", chunk="y"),
    ]
    plan = SynthesisPlan(thesis="th", tasks=[
        WorkerTask(focus="Casella", source_ranks=[1]),
        WorkerTask(focus="Wasserman", source_ranks=[2]),
    ])
    return sources, plan


def test_deep_synth_routes_to_skill_then_schema_fill(monkeypatch):
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    calls = {}

    async def fake_skill(query, srcs, briefs):
        calls["skill"] = True
        return "DEEPAGENTS SYNTH", 10, 20
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", fake_skill)

    async def fake_fill(query, text, model, cb):
        calls["fill_text"] = text
        return DeepTutorAnswer(tldr="ok", definition=text, formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_schema_fill", fake_fill)

    deep, _ = asyncio.run(OW.run_orchestrator_workers(
        "q", sources, plan, deep_synth=True))
    assert calls.get("skill") and calls["fill_text"] == "DEEPAGENTS SYNTH"
    assert deep.tldr == "ok"


def test_deep_synth_falls_back_to_L0_on_skill_failure(monkeypatch):
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    async def boom(query, srcs, briefs):
        raise RuntimeError("pip install deepagents")
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", boom)

    seen = {}

    async def fake_stream(messages, model, cb):
        seen["L0"] = True
        return DeepTutorAnswer(tldr="L0", definition="d", formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_stream_structured", fake_stream)

    deep, _ = asyncio.run(OW.run_orchestrator_workers(
        "q", sources, plan, deep_synth=True))
    assert seen.get("L0") and deep.tldr == "L0"


def test_deep_synth_falls_back_to_L0_when_schema_fill_returns_none(monkeypatch):
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    async def ok_skill(query, srcs, briefs):
        return "SYNTH", 10, 20
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", ok_skill)

    async def none_fill(query, text, model, cb):
        return None, {}
    monkeypatch.setattr(OW, "_schema_fill", none_fill)

    seen = {}
    async def fake_stream(messages, model, cb):
        seen["L0"] = True
        return DeepTutorAnswer(tldr="L0", definition="d", formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_stream_structured", fake_stream)

    deep, _ = asyncio.run(OW.run_orchestrator_workers("q", sources, plan, deep_synth=True))
    assert seen.get("L0") and deep.tldr == "L0"


def test_request_accepts_orchestrator_deep_workflow():
    from src.services.chat.schemas._core import ChatRequest
    req = ChatRequest(message="hi", tutorWorkflow="orchestrator-deep")
    assert req.tutorWorkflow == "orchestrator-deep"


def test_env_level_5_triggers_skill_path(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "5")
    sources, plan = _two_author_inputs()

    async def fake_worker(query, thesis, author, srcs, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum",
                           key_points=[f"{author} kp"], source_ranks=[srcs[0].rank])
    monkeypatch.setattr(OW, "run_author_worker", fake_worker)

    calls = {}
    async def fake_skill(query, srcs, briefs):
        calls["skill"] = True
        return "ENV SYNTH", 1, 2
    import src.services.chat.agents.ow_deepagents as OWD
    monkeypatch.setattr(OWD, "synthesize_with_skill", fake_skill)

    async def fake_fill(query, text, model, cb):
        calls["fill_text"] = text
        return DeepTutorAnswer(tldr="env-ok", definition=text, formal_statement="",
                               example_intuition="", applications="",
                               further_reading=""), {}
    monkeypatch.setattr(OW, "_schema_fill", fake_fill)

    deep, _ = asyncio.run(OW.run_orchestrator_workers("q", sources, plan))
    assert calls.get("skill") and calls["fill_text"] == "ENV SYNTH"
    assert deep.tldr == "env-ok"
