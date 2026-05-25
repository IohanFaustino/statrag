"""Tests for vision gate logic (src/services/chat/vision.py).

All LLM / Qdrant / OpenAI calls are patched out; these tests run fully offline.

Chinese-wall: imports only ``src.services.chat.*`` and stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.services.chat.schemas import Figure
from src.services.chat.vision import VisionDecision, VisionGateConfig, vision_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fig(ref: str = "f1") -> Figure:
    """Build a minimal Figure for testing."""
    return Figure(
        ref=ref,
        book="islp",
        chapter="ch06",
        caption="Bias-variance tradeoff",
        chart="https://example.com/fig.png",
    )


# ---------------------------------------------------------------------------
# Unit tests — gate thresholds
# ---------------------------------------------------------------------------


def test_skip_below_low() -> None:
    """Score below tau_low must yield 'skip'."""
    out = vision_gate(
        [_fig()],
        [0.3],
        config=VisionGateConfig(tau_low=0.45, tau_high=0.62),
    )
    assert len(out) == 1
    assert out[0].action == "skip"
    assert "tau_low" in out[0].reason


def test_caption_only_above_high() -> None:
    """Score at or above tau_high must yield 'caption_only'."""
    out = vision_gate([_fig()], [0.7])
    assert out[0].action == "caption_only"
    assert "caption sufficient" in out[0].reason


def test_caption_only_exactly_at_high() -> None:
    """Score exactly equal to tau_high is 'caption_only', not 'call_vision'."""
    out = vision_gate([_fig()], [0.62])
    assert out[0].action == "caption_only"


def test_call_vision_in_uncertain_range() -> None:
    """Score in [tau_low, tau_high) and within budget must yield 'call_vision'."""
    out = vision_gate([_fig()], [0.55])
    assert out[0].action == "call_vision"
    assert "uncertain" in out[0].reason


def test_call_vision_at_tau_low() -> None:
    """Score exactly at tau_low is in the uncertain range."""
    out = vision_gate(
        [_fig()],
        [0.45],
        config=VisionGateConfig(tau_low=0.45, tau_high=0.62),
    )
    assert out[0].action == "call_vision"


# ---------------------------------------------------------------------------
# Budget exhaustion
# ---------------------------------------------------------------------------


def test_budget_exhausts() -> None:
    """After max_calls vision decisions, excess uncertain figures become caption_only."""
    figs = [_fig(f"f{i}") for i in range(5)]
    scores = [0.5] * 5  # all in uncertain range
    out = vision_gate(figs, scores, config=VisionGateConfig(max_calls=2))
    actions = [d.action for d in out]
    assert actions.count("call_vision") == 2
    assert actions.count("caption_only") == 3


def test_budget_zero_means_no_vision_calls() -> None:
    """max_calls=0 should turn all uncertain figures into caption_only."""
    figs = [_fig(f"f{i}") for i in range(3)]
    scores = [0.55] * 3
    out = vision_gate(figs, scores, config=VisionGateConfig(max_calls=0))
    assert all(d.action == "caption_only" for d in out)


def test_budget_applies_only_to_uncertain_range() -> None:
    """Budget counter must not be decremented by skip or caption_only decisions."""
    figs = [_fig(f"f{i}") for i in range(4)]
    # f0: skip; f1: caption_only; f2+f3: uncertain (both should get call_vision w/ max=2)
    scores = [0.2, 0.9, 0.5, 0.55]
    out = vision_gate(figs, scores, config=VisionGateConfig(max_calls=2))
    actions = [d.action for d in out]
    assert actions[0] == "skip"
    assert actions[1] == "caption_only"
    assert actions[2] == "call_vision"
    assert actions[3] == "call_vision"


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


def test_returns_one_decision_per_figure() -> None:
    """Output length must match input length."""
    figs = [_fig(f"f{i}") for i in range(6)]
    scores = [0.1, 0.3, 0.45, 0.55, 0.62, 0.9]
    out = vision_gate(figs, scores)
    assert len(out) == len(figs)


def test_decision_carries_figure_reference() -> None:
    """Each VisionDecision must hold the correct Figure object."""
    fig = _fig("ref_xyz")
    out = vision_gate([fig], [0.55])
    assert out[0].figure is fig
    assert out[0].figure.ref == "ref_xyz"


def test_decision_carries_score() -> None:
    """Each VisionDecision must record the original score."""
    out = vision_gate([_fig()], [0.53])
    assert abs(out[0].score - 0.53) < 1e-9


def test_empty_input_returns_empty() -> None:
    """Empty lists produce empty output."""
    out = vision_gate([], [])
    assert out == []


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_custom_thresholds_shift_boundaries() -> None:
    """Raising tau_high should push more figures into call_vision."""
    out_default = vision_gate([_fig()], [0.65])
    assert out_default[0].action == "caption_only"

    out_custom = vision_gate(
        [_fig()], [0.65], config=VisionGateConfig(tau_high=0.80)
    )
    assert out_custom[0].action == "call_vision"


def test_reason_field_is_non_empty() -> None:
    """Every decision must have a non-empty reason string."""
    figs = [_fig(f"f{i}") for i in range(3)]
    scores = [0.2, 0.55, 0.9]
    for d in vision_gate(figs, scores):
        assert isinstance(d.reason, str) and d.reason.strip()


# ---------------------------------------------------------------------------
# Hand-labeled eval set (vision20.jsonl)
# ---------------------------------------------------------------------------


def test_precision_on_vision20() -> None:
    """Verify the hand-labeled set achieves precision >= 0.7 with a simple keyword proxy.

    Keyword classifier: query contains any token from a small trigger set.
    This is a sanity check on the eval data quality, not a model evaluation.
    """
    p = Path("data/eval/vision20.jsonl")
    if not p.exists():
        pytest.skip("vision20.jsonl not present")

    records: list[dict[str, Any]] = [
        json.loads(line) for line in p.read_text().splitlines() if line.strip()
    ]
    assert len(records) >= 20, f"Expected >=20 records, got {len(records)}"

    trigger_kw = {"show", "interpret", "what does", "axis", "curve", "plot indicates", "graph"}
    tp = fp = tn = fn = 0
    for r in records:
        q = r["query"].lower()
        pred = any(k in q for k in trigger_kw)
        actual = bool(r["vision_needed"])
        if pred and actual:
            tp += 1
        elif pred and not actual:
            fp += 1
        elif not pred and not actual:
            tn += 1
        else:
            fn += 1

    precision = tp / max(tp + fp, 1)
    assert precision >= 0.7, (
        f"Keyword classifier precision {precision:.2f} < 0.7 "
        f"(TP={tp}, FP={fp}, TN={tn}, FN={fn})"
    )
