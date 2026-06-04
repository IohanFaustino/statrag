"""Tests for the orchestrator-workers harness scaffold + eval helpers."""
import asyncio
import json as _json
from unittest.mock import patch

from src.services.chat.agents import orchestrator_workers as OW
from src.services.chat.agents import ow_harness as H
from src.services.chat.eval import ow_harness_compare as OWC
from src.services.chat.schemas import Source
from src.services.chat.schemas.output import AuthorBrief


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


def test_owc_constants_and_helpers():
    assert OWC.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert len(OWC.QUESTIONS) == 3
    assert OWC.JUDGE_DIMS == ("faithfulness", "coverage", "synthesis", "coherence")


def test_owc_render_briefs_text():
    from src.services.chat.schemas.output import AuthorBrief as AB
    txt = OWC._briefs_text([AB(author="Hansen", summary="s", key_points=["k1"])])
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


# ---------------------------------------------------------------------------
# Task 1 — harness helpers
# ---------------------------------------------------------------------------


def test_structured_briefs_block_is_json():
    briefs = [AuthorBrief(author="Hansen", summary="s1", key_points=["k1"], source_ranks=[1])]
    block = H.structured_briefs_block(briefs)
    assert "<author_briefs_json>" in block and "</author_briefs_json>" in block
    inner = block.split("<author_briefs_json>")[1].split("</author_briefs_json>")[0].strip()
    data = _json.loads(inner)
    assert data == [{"author": "Hansen", "summary": "s1", "key_points": ["k1"], "source_ranks": [1]}]


def test_content_bearing_filters_no_info():
    briefs = [
        AuthorBrief(author="A", summary="The source does not discuss this.", key_points=[]),
        AuthorBrief(author="B", summary="Real treatment.", key_points=["kp"]),
        AuthorBrief(author="C", summary="", key_points=[]),
    ]
    kept = H.content_bearing(briefs)
    assert [b.author for b in kept] == ["B"]


def test_max_level_is_five(monkeypatch):
    monkeypatch.setenv("TUTOR_OW_HARNESS", "5")
    assert H.ow_harness_level() == 5
    monkeypatch.setenv("TUTOR_OW_HARNESS", "6")
    assert H.ow_harness_level() == 0


# ---------------------------------------------------------------------------
# Task 2 — deepagents experiment module
# ---------------------------------------------------------------------------

def test_brief_md_formats():
    from src.services.chat.agents import ow_deepagents as DA
    md = DA._brief_md(AuthorBrief(author="Hansen", summary="sum", key_points=["k1", "k2"]))
    assert "Hansen" in md and "sum" in md and "k1" in md and "k2" in md


def test_deepagents_import_error_is_clear(monkeypatch):
    import sys
    from src.services.chat.agents import ow_deepagents as DA
    # Simulate deepagents missing.
    monkeypatch.setitem(sys.modules, "deepagents", None)
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_deepagents("q", [], []))


def test_synthesize_with_skill_import_error_is_clear(monkeypatch):
    """Invariant 35: synthesize_with_skill must also raise a clear RuntimeError
    (mentioning deepagents / pip install) when deepagents is absent."""
    import sys
    from src.services.chat.agents import ow_deepagents as DA
    monkeypatch.setitem(sys.modules, "deepagents", None)
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="deepagents"):
        asyncio.run(DA.synthesize_with_skill("q", [], []))


# ---------------------------------------------------------------------------
# Task 3 — wire L2 + L3 into the workflow
# ---------------------------------------------------------------------------

def test_level2_uses_structured_block(monkeypatch):
    from src.services.chat.agents import orchestrator_workers as OW
    from src.services.chat.schemas.output import AuthorBrief, DeepTutorAnswer
    monkeypatch.setenv("TUTOR_OW_HARNESS", "2")
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]
    captured = {}

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum", key_points=["kp"], source_ranks=[s[0].rank])

    async def fake_stream(messages, *a, **k):
        captured["user"] = messages[1]["content"]
        return DeepTutorAnswer(tldr="", definition="d", formal_statement="",
                               example_intuition="", applications="", further_reading=""), {}

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch.object(OW, "_stream_structured", side_effect=fake_stream):
        asyncio.run(OW.run_orchestrator_workers("q", srcs, None))
    assert "<author_briefs_json>" in captured["user"]


def test_level3_routes_to_deepagents(monkeypatch):
    from src.services.chat.agents import orchestrator_workers as OW
    from src.services.chat.schemas.output import AuthorBrief
    monkeypatch.setenv("TUTOR_OW_HARNESS", "3")
    srcs = [_src(1, "Hansen"), _src(2, "Wooldridge")]

    async def fake_worker(query, thesis, author, s, *, model=None):
        return AuthorBrief(author=author, summary=f"{author} sum", key_points=["kp"], source_ranks=[s[0].rank])

    async def fake_synth(query, sources, briefs):
        return "DEEPAGENTS SYNTHESIS TEXT"

    with patch.object(OW, "run_author_worker", side_effect=fake_worker), \
         patch("src.services.chat.agents.ow_deepagents.synthesize_with_deepagents", side_effect=fake_synth):
        ans, _ = asyncio.run(OW.run_orchestrator_workers("q", srcs, None))
    assert ans is not None and "DEEPAGENTS SYNTHESIS TEXT" in ans.definition


# ---------------------------------------------------------------------------
# Task 4 — eval scoped + content-bearing + levels
# ---------------------------------------------------------------------------

def test_owc_scoped_books_and_levels():
    assert OWC.BOOKS == ["hansen", "wooldridge", "stock_watson", "gujarati",
                         "baltagi", "pesaran", "islp", "murphy"]
    assert OWC.LEVELS == [0, 2, 3]


def test_owc_render_three_levels():
    base = {"qi": 0, "ok": True, "answer": "A", "briefs": "B", "in_tok": 1, "out_tok": 1,
            "ms": 1, "quality": {"faithfulness":4,"coverage":4,"synthesis":4,"coherence":4,"overall":4.0},
            "fidelity": 3.0}
    rows = {("L0", 0): {**base, "level": "L0"},
            ("L2", 0): {**base, "level": "L2"},
            ("L3", 0): {**base, "level": "L3"}}
    md = OWC._render_artifact(rows)
    assert "L0" in md and "L2" in md and "L3" in md


# ---------------------------------------------------------------------------
# Plan D — Change 1: synthesize_with_skill accepts model kwarg
# ---------------------------------------------------------------------------

def test_synthesize_with_skill_accepts_model_kwarg():
    import inspect
    from src.services.chat.agents.ow_deepagents import synthesize_with_skill
    assert "model" in inspect.signature(synthesize_with_skill).parameters


def test_fidelity_input_not_truncated():
    """Regression: the fidelity judge must see full briefs + full answer (the
    2500/3000 truncation cut most authors and falsely scored retained facts as
    dropped)."""
    big_briefs = "B" * 9000
    big_answer = "A" * 11000
    s = OWC._fidelity_input(big_briefs, big_answer)
    assert big_briefs in s and big_answer in s
    assert OWC._JUDGE_CHARS >= 12000
