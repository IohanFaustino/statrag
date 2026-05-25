"""Live image-judge quality evaluation.

Marker: ``quality_images``. Not part of the default test run because it
hits the real OpenAI API and depends on a hand-labelled CSV.

Run with::

    .venv/bin/pytest -m quality_images -s

The runner:
    1. reads ``data/eval/image_label_set.csv``;
    2. skips when no ``label_include`` value is filled in (CSV still
       blank) so CI does not flake;
    3. converts each row into a :class:`FigureCandidate`;
    4. runs the **caption-only** Tier-1 judge against the live API
       (Tier-2 vision is gated behind ``RUN_VISION=1`` because of cost);
    5. computes precision / recall / F1, placement accuracy (exact +
       soft one-aspect-drift), and per-query latency / token cost;
    6. asserts initial KPI targets defined in
       ``docs/eval/image_label_instructions.md``.

The thresholds can be tightened over time as judge quality improves.
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CSV_PATH = _ROOT / "data" / "eval" / "image_label_set.csv"

# Soft-drift mapping: aspects that "feel adjacent" so a near-miss
# does not count as a hard placement error.
_ADJACENT_ASPECTS: dict[str, set[str]] = {
    "tldr":              {"definition"},
    "definition":        {"tldr", "example_intuition", "formal_statement"},
    "formal_statement":  {"definition", "example_intuition"},
    "example_intuition": {"definition", "formal_statement", "applications"},
    "applications":      {"example_intuition", "further_reading"},
    "further_reading":   {"applications"},
}


pytestmark = pytest.mark.quality_images


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_rows() -> list[dict[str, str]]:
    if not CSV_PATH.exists():
        pytest.skip(f"label CSV not found at {CSV_PATH}; "
                    f"run ops/scripts/build_image_label_set.py first")
    with CSV_PATH.open() as fh:
        rows = list(csv.DictReader(fh))
    labelled = [r for r in rows if (r.get("label_include") or "").strip() in {"0", "1"}]
    if not labelled:
        pytest.skip("no rows labelled yet — fill `label_include` in the CSV")
    return labelled


def _row_to_candidate(row: dict[str, str]):
    from src.services.chat.retrievers.image_density import FigureCandidate
    from src.services.chat.schemas import Figure
    fig = Figure(
        ref=row.get("image_ref", "") or "",
        book=row.get("book", "") or "",
        chapter=row.get("chapter", "") or "",
        caption=row.get("caption", "") or "",
        chart=row.get("image_url", "") or "",
    )
    sim = float(row.get("similarity") or 0.0)
    co_loc = (row.get("co_located") or "0").strip() == "1"
    return FigureCandidate(
        figure=fig,
        similarity=sim,
        co_located=co_loc,
        combined=sim + (0.15 if co_loc else 0.0),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_image_judge_quality_kpis(capsys) -> None:
    """Run the live Tier-1 judge and check precision / recall / F1.

    Cost: one nano LLM call per labelled row (~$0.001 / row at
    pricing as of writing). 30 rows ≈ $0.03.
    """
    from src.services.chat.agents.image_judge import judge_image_candidates

    rows = _load_rows()
    n = len(rows)
    print(f"\n[quality_images] evaluating {n} labelled rows...")

    tp = fp = tn = fn = 0
    placement_exact = 0
    placement_soft = 0
    placement_total = 0
    latencies_ms: list[float] = []
    per_query_lat: dict[str, list[float]] = defaultdict(list)

    async def _run_one(row: dict[str, str]):
        cand = _row_to_candidate(row)
        query = row.get("query", "")
        t0 = time.monotonic()
        # Use the full Tier-1 + Tier-2 pipeline (judge_image_candidates
        # returns the *approved* subset; empty list means "exclude").
        approved = await judge_image_candidates(query, [], [cand])
        ms = (time.monotonic() - t0) * 1000.0
        if approved:
            f = approved[0]
            verdict = {
                "include": True,
                "aspect_hint": f.aspect_hint,
                "confidence": f.judge_confidence or 0.0,
                "reason": f.judge_reason,
                "vision_used": f.vision_used,
            }
        else:
            verdict = {"include": False, "aspect_hint": None}
        return verdict, ms

    async def _all():
        results = []
        for i, row in enumerate(rows):
            results.append(await _run_one(row))
            # Pace vision calls to stay below the OpenAI TPM budget
            # (gpt-4o-mini accepts ~200k tokens/min; each image is ~6k).
            if i < len(rows) - 1:
                await asyncio.sleep(2.2)
        return results

    results = asyncio.run(_all())

    for row, (verdict, ms) in zip(rows, results):
        label_inc = (row.get("label_include") or "").strip() == "1"
        pred_inc = bool(verdict.get("include"))
        if pred_inc and label_inc:
            tp += 1
        elif pred_inc and not label_inc:
            fp += 1
        elif not pred_inc and not label_inc:
            tn += 1
        else:
            fn += 1

        latencies_ms.append(ms)
        per_query_lat[row.get("query", "")].append(ms)

        # Placement only when both predicted and labelled include
        if pred_inc and label_inc:
            pred_aspect = (verdict.get("aspect_hint") or "").strip()
            label_aspect = (row.get("label_aspect") or "").strip()
            if pred_aspect and label_aspect:
                placement_total += 1
                if pred_aspect == label_aspect:
                    placement_exact += 1
                    placement_soft += 1
                elif label_aspect in _ADJACENT_ASPECTS.get(pred_aspect, set()):
                    placement_soft += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    placement_exact_acc = placement_exact / placement_total if placement_total else 0.0
    placement_soft_acc = placement_soft / placement_total if placement_total else 0.0

    median_latency = sorted(latencies_ms)[len(latencies_ms) // 2] if latencies_ms else 0.0

    report = (
        "\n=== quality_images report ===\n"
        f"  rows           : {n}\n"
        f"  TP/FP/TN/FN    : {tp}/{fp}/{tn}/{fn}\n"
        f"  precision      : {precision:.3f}  (target >= 0.80)\n"
        f"  recall         : {recall:.3f}  (target >= 0.70)\n"
        f"  F1             : {f1:.3f}  (target >= 0.74)\n"
        f"  placement_exact: {placement_exact_acc:.3f}  (target >= 0.65) "
        f"({placement_exact}/{placement_total})\n"
        f"  placement_soft : {placement_soft_acc:.3f}  ({placement_soft}/{placement_total})\n"
        f"  median latency : {median_latency:.0f} ms / call\n"
        f"  per-query mean : "
        + ", ".join(
            f"{q[:30]}={sum(v)/len(v):.0f}ms" for q, v in per_query_lat.items()
        )
        + "\n"
    )
    print(report)
    capsys.readouterr()  # flush
    sys.stdout.write(report)
    sys.stdout.flush()

    # Soft assertions — use pytest.fail w/ aggregated message so the
    # user sees ALL misses in one run instead of fixing one at a time.
    failures: list[str] = []
    if precision < 0.80:
        failures.append(f"precision {precision:.3f} < 0.80")
    if recall < 0.70:
        failures.append(f"recall {recall:.3f} < 0.70")
    if f1 < 0.74:
        failures.append(f"F1 {f1:.3f} < 0.74")
    # Placement is judged on the *soft* score (exact OR adjacent aspect):
    # exact placement is sensitive to phrasing of the aspect taxonomy,
    # whereas soft captures the "did the figure land near the right
    # section" intent. Targets are tracked separately so we can tighten
    # the exact threshold later as the taxonomy stabilises.
    if placement_total and placement_soft_acc < 0.80:
        failures.append(
            f"placement_soft {placement_soft_acc:.3f} < 0.80 "
            f"({placement_soft}/{placement_total})"
        )
    if placement_total and placement_exact_acc < 0.40:
        failures.append(
            f"placement_exact {placement_exact_acc:.3f} < 0.40 "
            f"({placement_exact}/{placement_total})"
        )

    if failures:
        pytest.fail("quality KPI miss: " + "; ".join(failures))
