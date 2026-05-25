"""Tests for the image pertinence pipeline (retriever + two-tier judge).

All external I/O (OpenAI, Qdrant) is mocked. The tests assert systematic
behaviour only; quality KPIs (precision / recall) require human-labelled
ground truth and live against ``data/eval/image_label_set.csv`` via the
nightly ``pytest -m quality_images`` lane (see
:mod:`docs/eval/image_label_instructions`).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fig(ref, book, chapter, caption, chart="/api/figures?path=x.png"):
    from src.services.chat.schemas import Figure
    return Figure(ref=ref, book=book, chapter=chapter, caption=caption, chart=chart)


def _src(rank, book, chapter, section, text):
    from src.services.chat.schemas import Source
    return Source(
        rank=rank, book=book, chapter=chapter, section=section,
        title=f"{book} §{section}", excerpt=text[:200], score=1.0 / rank,
        chunkId=f"{book}-{section}-{rank}", chunk=text,
        book_name=book.upper(), authors="Smith", authors_short="Smith",
        year=2024, page_from=10, page_to=12, page=10,
    )


def _cand(ref, book, chapter, caption, similarity=0.9, co_located=False):
    from src.services.chat.retrievers.image_density import FigureCandidate
    return FigureCandidate(
        figure=_fig(ref, book, chapter, caption),
        similarity=similarity, co_located=co_located,
        combined=similarity + (0.15 if co_located else 0.0),
    )


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------


def test_fetch_image_candidates_returns_empty_when_no_query():
    from src.services.chat.retrievers.image_density import fetch_image_candidates
    out = fetch_image_candidates("   ", [], book_slugs=None, pool=4)
    assert out == []


def test_fetch_image_candidates_co_location_boost(monkeypatch):
    from src.services.chat.retrievers import image_density

    sources = [_src(1, "islp", "ch02", "2.1", "bias variance content")]

    def fake_search(query, book_slugs=None, k=8):
        return [
            (_fig("f1", "islp", "ch02", "bias-variance diagram"), 0.55),
            (_fig("f2", "esl", "ch03", "decorative photo"), 0.60),
        ]

    monkeypatch.setattr(image_density, "search_figures_with_scores", fake_search)
    out = image_density.fetch_image_candidates(
        "bias variance", sources, book_slugs=None, pool=4,
    )
    # Co-located ISLP figure should outrank ESL even with lower raw score.
    assert out[0].figure.ref == "f1"
    assert out[0].co_located is True
    assert out[1].figure.ref == "f2"


def test_fetch_image_candidates_caps_pool(monkeypatch):
    from src.services.chat.retrievers import image_density

    def fake_search(query, book_slugs=None, k=8):
        return [(_fig(f"f{i}", "islp", "ch02", "cap"), 0.5) for i in range(10)]

    monkeypatch.setattr(image_density, "search_figures_with_scores", fake_search)
    out = image_density.fetch_image_candidates("q", [], pool=4)
    assert len(out) == 4


# ---------------------------------------------------------------------------
# Tier-1 caption judge
# ---------------------------------------------------------------------------


def _stub_async_create(content: str):
    async def _create(*a, **kw):
        return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])
    fake = MagicMock()
    fake.chat.completions.create = _create
    return fake


def test_tier1_excludes_short_caption():
    from src.services.chat.agents.image_judge import _judge_one_caption
    c = _cand("f", "a", "c", caption="x")
    out = asyncio.run(_judge_one_caption("query", ["topic"], c))
    assert out["include"] is False
    assert "short" in out["reason"].lower() or "empty" in out["reason"].lower()


def test_tier1_parses_verdict_json():
    from src.services.chat.agents import image_judge

    body = json.dumps({
        "include": True, "role": "diagram", "confidence": 0.85,
        "aspect_hint": "example_intuition", "reason": "shows worked example",
    })
    c = _cand("f", "a", "c", caption="A bias-variance tradeoff diagram")
    with patch.object(image_judge, "_aclient", return_value=_stub_async_create(body)):
        out = asyncio.run(image_judge._judge_one_caption("query", ["bias-variance"], c))
    assert out["include"] is True
    assert out["role"] == "diagram"
    assert out["aspect_hint"] == "example_intuition"
    assert 0.0 <= out["confidence"] <= 1.0


def test_tier1_handles_invalid_json_gracefully():
    from src.services.chat.agents import image_judge

    c = _cand("f", "a", "c", caption="A diagram with sufficient length text")
    with patch.object(image_judge, "_aclient", return_value=_stub_async_create("not json")):
        out = asyncio.run(image_judge._judge_one_caption("q", [], c))
    assert out["include"] is False  # default exclude on parser failure
    assert "error" in out["reason"].lower() or out["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Two-tier orchestration
# ---------------------------------------------------------------------------


def test_judge_caps_max_figures():
    from src.services.chat.agents import image_judge

    cands = [_cand(f"f{i}", "a", "c", f"diagram caption {i} substantive") for i in range(6)]

    async def fake_t1(query, concepts, cand, t1_model=None):
        return {"include": True, "role": "diagram", "confidence": 0.9,
                "aspect_hint": "example_intuition", "reason": "ok"}

    with patch.object(image_judge, "_judge_one_caption", fake_t1), \
         patch.object(image_judge, "_MAX_FIGURES", 3):
        out = asyncio.run(image_judge.judge_image_candidates("q", [], cands))
    assert len(out) == 3
    assert all(f.aspect_hint == "example_intuition" for f in out)
    assert all(f.judge_confidence >= 0.7 for f in out)


def test_judge_skips_vision_when_confident_exclude():
    from src.services.chat.agents import image_judge

    cands = [_cand("f1", "a", "c", "decorative photo of skyline")]

    async def fake_t1(query, concepts, cand, t1_model=None):
        return {"include": False, "role": "photo", "confidence": 0.3,
                "aspect_hint": None, "reason": "decorative"}

    vision_calls = {"n": 0}
    async def fake_t2(query, cand, tier1):
        vision_calls["n"] += 1
        return tier1

    with patch.object(image_judge, "_judge_one_caption", fake_t1), \
         patch.object(image_judge, "_judge_one_vision", fake_t2):
        out = asyncio.run(image_judge.judge_image_candidates("q", [], cands))
    assert out == []
    assert vision_calls["n"] == 0


def test_judge_runs_vision_on_borderline():
    from src.services.chat.agents import image_judge

    cands = [_cand("f1", "a", "c", "ambiguous caption requires vision check")]

    async def fake_t1(query, concepts, cand, t1_model=None):
        return {"include": True, "role": "diagram", "confidence": 0.55,
                "aspect_hint": "definition", "reason": "borderline"}

    async def fake_t2(query, cand, tier1):
        return {**tier1, "include": True, "confidence": 0.92,
                "vision_used": True, "reason": "vision confirms diagram"}

    with patch.object(image_judge, "_judge_one_caption", fake_t1), \
         patch.object(image_judge, "_judge_one_vision", fake_t2), \
         patch.object(image_judge, "_TIER2_ENABLED", True), \
         patch.object(image_judge, "_TIER2_MAX_CALLS", 2):
        out = asyncio.run(image_judge.judge_image_candidates("q", [], cands))
    assert len(out) == 1
    assert out[0].vision_used is True
    assert out[0].judge_confidence >= 0.9


def test_judge_respects_vision_disabled():
    from src.services.chat.agents import image_judge

    cands = [_cand("f1", "a", "c", "borderline caption text")]

    async def fake_t1(query, concepts, cand, t1_model=None):
        return {"include": False, "role": "other", "confidence": 0.55,
                "aspect_hint": None, "reason": "borderline"}

    async def fake_t2(query, cand, tier1):
        raise AssertionError("vision should not be called when disabled")

    with patch.object(image_judge, "_judge_one_caption", fake_t1), \
         patch.object(image_judge, "_judge_one_vision", fake_t2), \
         patch.object(image_judge, "_TIER2_ENABLED", False):
        out = asyncio.run(image_judge.judge_image_candidates("q", [], cands))
    assert out == []  # borderline + no vision = exclude


def test_judge_handles_empty_candidate_list():
    from src.services.chat.agents.image_judge import judge_image_candidates
    out = asyncio.run(judge_image_candidates("q", [], []))
    assert out == []


# ---------------------------------------------------------------------------
# FigureRef schema integration
# ---------------------------------------------------------------------------


def test_figure_ref_has_aspect_and_role_fields():
    from src.services.chat.schemas.output import FigureRef
    fr = FigureRef(ref="r", book="b", chapter="c", caption="cap",
                   aspect_hint="example_intuition", figure_role="graph",
                   judge_confidence=0.82, judge_reason="ok")
    assert fr.aspect_hint == "example_intuition"
    assert fr.figure_role == "graph"
    assert fr.judge_confidence == 0.82
    assert fr.judge_reason == "ok"


def test_figure_ref_defaults_safe_for_legacy_callers():
    from src.services.chat.schemas.output import FigureRef
    fr = FigureRef(ref="r", book="b", chapter="c", caption="cap")
    assert fr.aspect_hint is None
    assert fr.figure_role is None
    assert fr.judge_confidence is None
