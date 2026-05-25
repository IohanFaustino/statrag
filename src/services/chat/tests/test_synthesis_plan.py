"""Tests for the deep-tutor synthesis-plan step (workflow A)."""
import pytest

from src.services.chat.schemas import Source
from src.services.chat.schemas.output import AuthorContrast, SynthesisPlan, WorkerTask
from src.services.chat.agents import deep_tutor as d


def _src(rank=1, author="Smith", book="b1"):
    return Source(
        rank=rank, chunkId=f"c{rank}", title="T", excerpt="x", chunk="hello world",
        book=book, book_name="Book", authors=f"A {author}", authors_short=author,
        section="1", chapter="ch1", score=0.5,
    )


class TestSynthesisPlanModel:
    def test_parses_full(self):
        p = SynthesisPlan(
            thesis="one throughline",
            contrasts=[AuthorContrast(topic="t", author_a="A", position_a="pa",
                                      author_b="B", position_b="pb")],
            tasks=[WorkerTask(focus="A's view", source_ranks=[1])],
        )
        assert p.thesis and p.tasks[0].source_ranks == [1]

    def test_tolerates_missing_optionals(self):
        p = SynthesisPlan(thesis="t")
        assert p.contrasts == [] and p.tasks == []


class TestResolvePlanModel:
    def test_off_disables(self):
        assert d._resolve_plan_model({"plan": "off"}) == (False, "")
        assert d._resolve_plan_model({"plan": "OFF"}) == (False, "")

    def test_absent_uses_env_default(self):
        enabled, model = d._resolve_plan_model({})
        assert enabled == d._SYNTHESIS_PLAN_ON
        assert model  # a default model id

    def test_unknown_model_falls_back_enabled(self):
        enabled, _ = d._resolve_plan_model({"plan": "not-a-real-model"})
        assert enabled == d._SYNTHESIS_PLAN_ON


class TestBuildUserMessage:
    def test_includes_plan_blocks_when_present(self):
        plan = SynthesisPlan(
            thesis="T",
            contrasts=[AuthorContrast(topic="def", author_a="Smith", position_a="x",
                                      author_b="Jones", position_b="y")],
            tasks=[WorkerTask(focus="Smith's framing", source_ranks=[1])],
        )
        msg = d._build_user_message("q", [_src()], plan=plan)
        assert "<synthesis_plan>" in msg
        assert "thesis: T" in msg
        assert "angle: Smith's framing" in msg
        assert "<contrasts>" in msg

    def test_omits_plan_blocks_when_none(self):
        msg = d._build_user_message("q", [_src()], plan=None)
        assert "<synthesis_plan>" not in msg

    def test_empty_plan_renders_nothing(self):
        assert d._format_plan_block(SynthesisPlan()) == ""


@pytest.mark.asyncio
async def test_build_synthesis_plan_graceful_on_failure(monkeypatch):
    """Any client error -> None (caller proceeds without a plan)."""
    class _Boom:
        class chat:
            class completions:
                @staticmethod
                async def parse(*a, **k):
                    raise RuntimeError("boom")
    monkeypatch.setattr(d, "_async_client", lambda: _Boom())
    out = await d.build_synthesis_plan("q", [_src()], model="x")
    assert out is None


@pytest.mark.asyncio
async def test_build_synthesis_plan_empty_sources_returns_none():
    assert await d.build_synthesis_plan("q", []) is None


def test_structured_output_models_are_openai_strict_safe():
    """Guard: models used as OpenAI `response_format` must have NO open-keyed
    dict fields (strict structured outputs reject `additionalProperties` object
    schemas). This is the bug that silently disabled the Planner."""
    import json
    from src.services.chat.schemas.output import (
        SynthesisPlan, AuthorBrief, WorkerTask, OrchestratorPlan, DeepTutorAnswer,
    )
    def has_open_object(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and isinstance(node.get("additionalProperties"), dict):
                return True
            return any(has_open_object(v) for v in node.values())
        if isinstance(node, list):
            return any(has_open_object(v) for v in node)
        return False
    for model in (SynthesisPlan, AuthorBrief, WorkerTask, OrchestratorPlan, DeepTutorAnswer):
        schema = model.model_json_schema()
        assert not has_open_object(schema), f"{model.__name__} has an open-keyed dict field (breaks OpenAI strict structured outputs)"
