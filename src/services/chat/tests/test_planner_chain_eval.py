"""CI unit tests for the planner-chain eval (pure helpers only)."""
from src.services.chat.eval import planner_chain_compare as pc


def test_constants():
    assert pc.MODELS == ["gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus"]
    assert pc.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert len(pc.QUESTIONS) == 3
    assert pc.JUDGE_DIMS == ("decomposition", "coverage", "targeting", "redundancy")
    assert pc.MAX_TOK == 300 and pc.TIMEOUT_S == 60


def test_render_plan_text():
    txt = pc._render_plan({"sub_questions": ["a", "b"], "concepts": ["c"],
                           "perspectives": 2, "facets": ["f"], "queries": ["q"]})
    for needle in ("a", "b", "c", "f", "q", "2"):
        assert needle in txt


def test_parse_judge_ok_and_fallback():
    good = '{"decomposition":4,"coverage":5,"targeting":3,"redundancy":4}'
    d = pc._parse_judge(good)
    assert d["overall"] == 4.0
    assert pc._parse_judge("junk")["overall"] == 0.0


def test_render_artifact_has_rows():
    results = {
        ("gpt-5.4-nano-2026-03-17", 0): {
            "label": "nano-chain", "plan_text": "PLAN A", "in_tok": 100, "out_tok": 50,
            "ms": 900, "ok": True, "err": "",
            "scores": {"decomposition": 5, "coverage": 5, "targeting": 4, "redundancy": 4, "overall": 4.5}},
    }
    md = pc._render_artifact(results)
    assert "| contestant | question |" in md
    assert "nano-chain" in md and "4.5" in md and "$" in md
