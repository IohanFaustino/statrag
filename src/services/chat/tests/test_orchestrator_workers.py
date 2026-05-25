"""Tests for the orchestrator-workers (per-author) drafting workflow."""
import pytest

from src.services.chat.schemas import ChatRequest, Source
from src.services.chat.schemas.output import AuthorBrief, SynthesisPlan
from src.services.chat.agents import deep_tutor as d
from src.services.chat.agents import orchestrator_workers as ow


def _src(rank, author, book):
    return Source(
        rank=rank, chunkId=f"c{rank}", title="t", excerpt="x", chunk="hello",
        book=book, book_name=book, authors=f"A {author}", authors_short=author,
        section="1", chapter="ch1", score=0.5,
    )


def test_group_sources_by_author():
    g = ow._group_sources_by_author([
        _src(1, "Smith", "b1"), _src(2, "Jones", "b2"), _src(3, "Smith", "b1"),
    ])
    assert {k: len(v) for k, v in g.items()} == {"smith": 2, "jones": 1}


class TestResolveWorkflow:
    def test_default_single(self):
        assert d._resolve_workflow(ChatRequest(message="q")) == "single"

    def test_request_orchestrator(self):
        assert d._resolve_workflow(
            ChatRequest(message="q", tutorWorkflow="orchestrator")) == "orchestrator"


@pytest.mark.asyncio
async def test_worker_graceful_on_failure(monkeypatch):
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                async def parse(*a, **k):
                    raise RuntimeError("boom")
    monkeypatch.setattr(ow, "_async_client", lambda *_a, **_k: _Boom())
    out = await ow.run_author_worker("q", "thesis", "Smith", [_src(1, "Smith", "b1")])
    assert out is None


def test_fallback_tasks_per_author():
    tasks = ow._fallback_tasks([_src(1, "Smith", "b1"), _src(2, "Jones", "b2"), _src(3, "Smith", "b1")])
    assert {t.focus for t in tasks} == {"Smith", "Jones"}
    smith = next(t for t in tasks if t.focus == "Smith")
    assert sorted(smith.source_ranks) == [1, 3]


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_single_author():
    # No plan tasks -> per-author fallback -> 1 author -> (None, {}).
    out, aspects = await ow.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Smith", "b1")], None,
    )
    assert out is None and aspects == {}


@pytest.mark.asyncio
async def test_orchestrator_falls_back_when_all_workers_fail(monkeypatch):
    async def _none(*a, **k):
        return None
    monkeypatch.setattr(ow, "run_author_worker", _none)
    # plan has no tasks -> per-author fallback (2 authors) -> all workers fail.
    out, _ = await ow.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Jones", "b2")], SynthesisPlan(thesis="T"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_orchestrator_uses_planner_tasks(monkeypatch):
    # The Planner's tasks (plan.tasks) drive the workers — no second LLM call.
    from src.services.chat.schemas.output import WorkerTask, DeepTutorAnswer
    seen = []
    async def _worker(query, thesis, focus, srcs, *, model=None):
        seen.append(focus)
        return AuthorBrief(author=focus, summary="s", key_points=["p"], source_ranks=[srcs[0].rank])
    async def _synth(messages, model, on_aspect_delta=None):
        return DeepTutorAnswer(tldr="x", definition="d", formal_statement="f",
                               example_intuition="ei", applications="a",
                               further_reading="r"), {}
    monkeypatch.setattr(ow, "run_author_worker", _worker)
    monkeypatch.setattr(ow, "_stream_structured", _synth)
    plan = SynthesisPlan(thesis="T", tasks=[
        WorkerTask(focus="view A", source_ranks=[1]),
        WorkerTask(focus="view B", source_ranks=[2]),
    ])
    out, _ = await ow.run_orchestrator_workers(
        "q", [_src(1, "Smith", "b1"), _src(2, "Jones", "b2")], plan,
    )
    assert out is not None
    assert seen == ["view A", "view B"]  # planner-chosen foci drove the workers


def test_format_author_briefs():
    txt = ow._format_author_briefs([
        AuthorBrief(author="Smith", summary="S", key_points=["p1"], source_ranks=[1, 3]),
    ])
    assert "<author_briefs>" in txt and "author='Smith'" in txt and "#1, #3" in txt
