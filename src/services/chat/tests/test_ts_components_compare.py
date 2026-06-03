# src/services/chat/tests/test_ts_components_compare.py
"""Unit tests for the time-series-components comparison eval (pure helpers only)."""
from src.services.chat.eval import ts_components_compare as tc


def test_constants_present():
    assert "components of a time series" in tc.QUESTION.lower()
    assert tc.BOOKS == ["cerqueira", "spark_ts", "pesaran"]
    assert tc.JUDGE_MODEL == "gpt-5.4-nano-2026-03-17"
    assert tc.API_MODELS == [
        "gpt-5.4-nano-2026-03-17", "gemini-2.5-flash", "qwen-plus",
    ]
    for c in ("trend", "seasonal", "cyclical", "irregular"):
        assert any(c in g.lower() for g in tc.GOLD_COMPONENTS)
    assert tc.MAX_TOK == 700
    assert tc.TIMEOUT_S == 60


def test_prompt_mentions_question_and_json():
    assert "components of a time series" in tc.ANSWER_PROMPT.lower()
    assert '"reasoning"' in tc.ANSWER_PROMPT
    assert '"answer"' in tc.ANSWER_PROMPT


def test_contestant_filename_map():
    assert tc.CONTESTANT_FILE["gpt-5.4-nano-2026-03-17"] == "nano.json"
    assert tc.CONTESTANT_FILE["sonnet"] == "sonnet.json"
    assert tc.CONTESTANT_FILE["opus"] == "opus.json"
