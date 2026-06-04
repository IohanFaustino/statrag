"""CI unit tests for the Plan C deepagents comparison (pure helpers only)."""
import asyncio
import sys

import pytest

from src.services.chat.agents import ow_deepagents as DA
from src.services.chat.eval import ow_deepagents_compare as PC


def test_sum_usage_totals():
    meta = {"gpt-5.4-nano-2026-03-17": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            "other": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
    assert DA._sum_usage(meta) == (110, 45)


def test_sum_usage_empty():
    assert DA._sum_usage({}) == (0, 0)
    assert DA._sum_usage(None) == (0, 0)


def test_synthesis_skill_exists_and_well_formed():
    from pathlib import Path
    p = Path(DA.__file__).parent / "ow_skills" / "synthesis" / "SKILL.md"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert txt.startswith("---")          # frontmatter
    assert "name:" in txt and "description:" in txt
    assert "/briefs/" in txt              # tells the agent where the briefs are
    assert DA.SYNTHESIS_SKILL_DIR == str(p.parent.parent)  # ".../ow_skills"


def test_skill_arm_import_guard(monkeypatch):
    monkeypatch.setitem(sys.modules, "deepagents", None)
    with pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_skill("q", [], []))


def test_subagents_arm_import_guard(monkeypatch):
    monkeypatch.setitem(sys.modules, "deepagents", None)
    with pytest.raises(RuntimeError, match="pip install deepagents"):
        asyncio.run(DA.synthesize_with_subagents("q", [], []))


def test_pc_constants():
    assert PC.ARMS == ["L0", "L3a", "L3b", "L4"]
    assert len(PC.QUESTIONS) == 6
    assert PC.RUNS == 3
    assert PC.JUDGE_DIMS == ("faithfulness", "coverage", "synthesis", "coherence")


def test_pc_aggregate_mean_and_spread():
    runs = [{"overall": 4.0, "fidelity": 5.0, "in_tok": 100, "out_tok": 50, "ms": 1000},
            {"overall": 3.0, "fidelity": 4.0, "in_tok": 120, "out_tok": 60, "ms": 1200},
            {"overall": 5.0, "fidelity": 5.0, "in_tok": 110, "out_tok": 55, "ms": 1100}]
    agg = PC._aggregate(runs)
    assert agg["overall_mean"] == 4.0
    assert agg["overall_min"] == 3.0 and agg["overall_max"] == 5.0
    assert agg["fidelity_mean"] == round((5+4+5)/3, 2)
    assert agg["in_tok_mean"] == 110 and agg["out_tok_mean"] == 55


def test_pc_render_artifact():
    agg = {("L0", 0): {"overall_mean": 3.9, "overall_min": 3.5, "overall_max": 4.2,
                       "fidelity_mean": 4.6, "in_tok_mean": 800, "out_tok_mean": 600,
                       "ms_mean": 3000, "usd_mean": 0.0009, "ok_runs": 3}}
    md = PC._render_artifact(agg)
    assert "| arm | question |" in md and "L0" in md and "3.9" in md and "±" in md
