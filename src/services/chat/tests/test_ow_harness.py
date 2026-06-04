"""Tests for the orchestrator-workers harness scaffold + eval helpers."""
import asyncio
from unittest.mock import patch
from src.services.chat.agents import orchestrator_workers as OW
from src.services.chat.schemas.output import AuthorBrief
from src.services.chat.schemas import Source


def _src(rank, author):
    return Source(rank=rank, book="b", chapter="c", section="s", title="t",
                  excerpt="", score=1.0, chunkId=f"x{rank}", chunk="text",
                  authors_short=author)


def test_on_briefs_hook_receives_briefs():
    captured = {}
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} summary",
                           key_points=[f"{author} kp"], source_ranks=[s[0].rank])

    async def fake_stream(*a, **k):
        from src.services.chat.schemas.output import DeepTutorAnswer
        return DeepTutorAnswer(
            tldr="t", definition="d", formal_statement="",
            example_intuition="e", applications="a", further_reading="f"
        ), {}

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch.object(OW, "_stream_structured", side_effect=fake_stream):
        OW.run_orchestrator_workers
        ans, _ = asyncio.run(OW.run_orchestrator_workers(
            "q", srcs, None, on_briefs=lambda b: captured.setdefault("briefs", b)))
    assert "briefs" in captured
    assert {b.author for b in captured["briefs"]} == {"Hansen", "Wooldridge"}


from src.services.chat.agents import ow_harness as H


def test_level_parse_default_and_clamp(monkeypatch):
    monkeypatch.delenv("TUTOR_OW_HARNESS", raising=False)
    assert H.ow_harness_level() == 0
    monkeypatch.setenv("TUTOR_OW_HARNESS", "2")
    assert H.ow_harness_level() == 2
    monkeypatch.setenv("TUTOR_OW_HARNESS", "9")
    assert H.ow_harness_level() == 0
    monkeypatch.setenv("TUTOR_OW_HARNESS", "junk")
    assert H.ow_harness_level() == 0


def test_maybe_traced_is_passthrough_when_off(monkeypatch):
    monkeypatch.delenv("TUTOR_OW_HARNESS", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    def f(x):
        return x + 1

    wrapped = H.maybe_traced(f, name="f")
    assert wrapped is f or wrapped(1) == 2


def test_maybe_traced_preserves_behavior_when_on(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "1")
    monkeypatch.setenv("LANGSMITH_API_KEY", "fake")

    def f(x):
        return x * 3

    wrapped = H.maybe_traced(f, name="f")
    assert wrapped(2) == 6


from src.services.chat.eval import ow_harness_compare as OWC


def test_owc_constants_and_helpers():
    assert OWC.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert len(OWC.QUESTIONS) == 3
    assert OWC.JUDGE_DIMS == ("faithfulness", "coverage", "synthesis", "coherence")


def test_owc_render_briefs_text():
    from src.services.chat.schemas.output import AuthorBrief
    txt = OWC._briefs_text([AuthorBrief(author="Hansen", summary="s", key_points=["k1"])])
    assert "Hansen" in txt and "k1" in txt


def test_owc_parse_scores_fallback():
    d = OWC._parse_scores("garbage", OWC.JUDGE_DIMS)
    assert d["overall"] == 0.0
    good = '{"faithfulness":5,"coverage":4,"synthesis":4,"coherence":5}'
    g = OWC._parse_scores(good, OWC.JUDGE_DIMS)
    assert g["overall"] == 4.5


def test_owc_render_artifact():
    rows = {("L0", 0): {"level": "L0", "qi": 0, "ok": True, "answer": "A", "briefs": "B",
                        "in_tok": 10, "out_tok": 5, "ms": 100,
                        "quality": {"faithfulness":5,"coverage":4,"synthesis":4,"coherence":5,"overall":4.5},
                        "fidelity": 4.0}}
    md = OWC._render_artifact(rows)
    assert "| level | question |" in md and "L0" in md and "4.5" in md and "fidelity" in md.lower()
